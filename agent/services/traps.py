"""The subtle traps in the evidence, counted: the cases where a quick read says "compliant" and the records say otherwise.

The problem statement names them: a consent captured after the first message, time zones that differ between systems, one recording missing from a
series of calls. Each trap here is a pattern in the findings the checks already produced (from the finding's own wording, or from the records it
cites), so the counts are exactly what the audit reported, grouped by why a hurried reader would miss it. Nothing here decides a result.
"""
from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb

from agent.core.db import connect

# key, check type, status, text the reason contains, what the trap is, why it is easy to miss
TRAPS = [
    ("late_consent", "consent_before_contact", "gap", "consent was only recorded after it", "Consent captured after the message",
     "A consent record exists, so a quick look says the borrower consented. Its timestamp is later than the message."),
    ("wrong_purpose", "consent_before_contact", "gap", "only had consent for", "Consent given for a different purpose",
     "The number has consent on file, but for collections, not for the promotional or service message that was sent."),
    ("withdrawn", "consent_before_contact", "gap", "was withdrawn before it", "Consent withdrawn before the message",
     "Consent was once granted. It was withdrawn before the message went out."),
    ("timezone", "calling_hours", "gap", "UTC), outside the permitted", "Logged in UTC, judged in India time",
     "One dialer logs in UTC and the other in India time; the calling window is in India time. Read the logged clock at face value and these calls look in-window."),
    ("series", "recording_completeness", "gap", "has no recording", "One recording missing from a series of calls",
     "The account has recordings for its other calls, so the set looks complete. This connected call has none."),
    ("lapsed", "agent_certification", "gap", "was not valid on that date", "Certificate lapsed before the call",
     "The collector is on the register and was certified at some point. The certificate was not valid on the day they called."),
    ("late_identity", "verification_before_disclosure", "gap", "verified only at", "Identity verified, but after dues were disclosed",
     "The call has an identity check, so it looks verified. It came after the first disclosure of dues."),
    ("late_notice", "notice_timeline", "gap", "business days after the trigger", "Notice dispatched or served late",
     "Days are counted in business days, skipping weekends and holidays, from the date the notice was triggered."),
    ("tpl_early", "template_approval", "gap", "before the template was approved", "Message sent before its template was approved",
     "The template is approved now, so the registry looks fine. It was approved after this message went out."),
    ("tpl_status", "template_approval", "gap", "in the registry", "Message sent on a template that was never approved",
     "The template exists and was used, but the registry shows it as pending, rejected or expired."),
    ("terminated", "collector_active", "gap", "terminated since", "Call by a collector after they were terminated",
     "The collector has a valid certificate and a login. The status history shows they had left before the call."),
    ("personal_mobile", "caller_id_registered", "gap", "not on", "Call from a number that was never registered",
     "The dialer logged the call normally. The number it came from is not on the agency's registered list, so it is a personal mobile."),
    ("third_party", "third_party_disclosure", "gap", "reference contact and disclosed dues", "Dues disclosed to a reference contact",
     "The number belongs to someone the borrower named, not the borrower. The transcript shows dues were disclosed to them."),
    ("unreadable", None, "cannot_determine", "RETRIEVAL_FAILED", "Evidence that could not be read: no claim made",
     "The recording store returned an error. The platform does not call these compliant; it reports them as cannot determine and queues a follow-up."),
]


def compute(run_id: UUID) -> list[dict]:
    """Count the traps in one audit's findings: each trap with how many findings fall in it, one example to open, and (time-zone trap) how many a
    face-value read of the logged clock would have missed."""
    where, args = "f.run_id = %s", [run_id]
    out = []
    with connect() as conn:
        for key, check_type, status, text, label, why in TRAPS:
            extra, params = "", [status, f"%{text}%", *args]
            if check_type:
                extra, params = "AND c.check_type = %s", [status, f"%{text}%", check_type, *args]
            if key == "series":  # only when the account's other calls do have recordings
                extra += """ AND EXISTS (SELECT 1 FROM staging.call_sessions o JOIN staging.recordings r ON r.session_key = o.session_key
                                          WHERE o.account_id = f.account_id AND r.storage_status = 'AVAILABLE' AND o.session_key <> f.subject_ref)"""
            row = conn.execute(f"""SELECT count(*) AS n, min(f.finding_id) AS example FROM audit.findings f JOIN audit.checks c USING (run_id, check_id)
                                   WHERE f.status = %s AND f.reason ILIKE %s {extra} AND {where}""", params).fetchone()
            if not row["n"]:
                continue
            item = {"key": key, "count": row["n"], "example_finding": row["example"], "extra": {}}
            if key == "timezone":
                item["extra"]["face_value_misses"] = conn.execute(
                    """SELECT count(*) AS n FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) JOIN staging.call_sessions s ON s.session_key = f.subject_ref
                       WHERE f.status = 'gap' AND c.check_type = 'calling_hours' AND s.started_ts_src_tz = 'UTC'
                         AND EXTRACT(hour FROM s.started_ts_src::timestamp) BETWEEN 8 AND 18 AND f.run_id = %s""", args).fetchone()["n"]
            out.append(item)
    return out


def store(run_id: UUID) -> list[dict]:
    """Count a completed audit's traps and keep the counts."""
    items = compute(run_id)
    with connect() as conn, conn.transaction():
        conn.execute("DELETE FROM audit.run_traps WHERE run_id = %s", (run_id,))
        conn.cursor().executemany("INSERT INTO audit.run_traps (run_id, trap_key, n, example_finding, extra) VALUES (%s, %s, %s, %s, %s)",
                                  [(run_id, i["key"], i["count"], i["example_finding"], Jsonb(i["extra"])) for i in items] or [(run_id, "_none", 0, None, Jsonb({}))])  # a marker: counted, nothing found
    return items


def _decorate(rows: dict[str, dict]) -> list[dict]:
    meta = {t[0]: t for t in TRAPS}
    out = []
    for key, r in rows.items():
        _, check_type, status, text, label, why = meta[key]
        out.append({"key": key, "label": label, "why": why, "count": r["count"], "example_finding": r["example_finding"], "example_run": r["example_run"], "text": text,
                    "status": status, "check_type": check_type, **r["extra"]})
    return sorted(out, key=lambda t: -t["count"])


def trap_counts(run_id: UUID | None = None) -> list[dict]:
    """The traps caught in one audit, or summed over every completed audit. Counted on first use for an audit that has none stored yet."""
    with connect() as conn:
        runs = [run_id] if run_id else [r["run_id"] for r in conn.execute("SELECT run_id FROM audit.runs WHERE status = 'completed' AND kind = 'audit'")]
        have = {r["run_id"] for r in conn.execute("SELECT DISTINCT run_id FROM audit.run_traps WHERE run_id = ANY(%s)", (runs,))}
    for r in runs:
        if r not in have:
            store(r)  # a completed audit never changes, so it is counted once
    rows: dict[str, dict] = {}
    with connect() as conn:
        for r in conn.execute("SELECT run_id, trap_key, n, example_finding, extra FROM audit.run_traps WHERE run_id = ANY(%s) ORDER BY run_id", (runs,)):
            if r["trap_key"] == "_none":
                continue
            cur = rows.setdefault(r["trap_key"], {"count": 0, "example_finding": r["example_finding"], "example_run": str(r["run_id"]), "extra": {}})
            cur["count"] += r["n"]
            for k, v in (r["extra"] or {}).items():
                cur["extra"][k] = cur["extra"].get(k, 0) + v
    return _decorate(rows)
