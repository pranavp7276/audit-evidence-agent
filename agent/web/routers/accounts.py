"""Account files: everything tested for one sampled account."""

from uuid import UUID

from fastapi import APIRouter

from agent.core.db import read_rows
from agent.web.common import _LATEST_REVIEW, _all, _one, _run_or_404

router = APIRouter()


@router.get("/api/runs/{run_id}/accounts")
def accounts(run_id: UUID, q: str = "", only_gaps: bool = False, limit: int = 100, offset: int = 0) -> dict:
    _run_or_404(run_id)
    having = "HAVING count(f.*) FILTER (WHERE f.status = 'gap') > 0" if only_gaps else ""
    rows = _all(f"""
        SELECT s.account_id, s.account_number, count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
               count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
               COALESCE(array_agg(DISTINCT c.question_ref ORDER BY c.question_ref) FILTER (WHERE f.status = 'gap'), '{{}}') AS gap_questions
        FROM (SELECT DISTINCT sa.account_id, a.account_number FROM audit.sample_accounts sa LEFT JOIN staging.accounts a ON a.account_id = sa.account_id
              WHERE sa.run_id = %s AND (sa.account_id ILIKE %s OR a.account_number ILIKE %s)) s
        LEFT JOIN audit.findings f ON f.run_id = %s AND f.account_id = s.account_id
        LEFT JOIN audit.checks c ON c.run_id = f.run_id AND c.check_id = f.check_id
        GROUP BY s.account_id, s.account_number {having} ORDER BY gaps DESC, s.account_id LIMIT %s OFFSET %s""",
                (run_id, f"%{q.strip()}%", f"%{q.strip()}%", run_id, max(1, min(limit, 500)), max(0, offset)))
    total = _one(f"""SELECT count(*) AS n FROM (SELECT s.account_id FROM (SELECT DISTINCT sa.account_id, a.account_number FROM audit.sample_accounts sa
                     LEFT JOIN staging.accounts a ON a.account_id = sa.account_id
                     WHERE sa.run_id = %s AND (sa.account_id ILIKE %s OR a.account_number ILIKE %s)) s
                     LEFT JOIN audit.findings f ON f.run_id = %s AND f.account_id = s.account_id
                     GROUP BY s.account_id {having}) t""", (run_id, f"%{q.strip()}%", f"%{q.strip()}%", run_id))["n"]
    return {"total": total, "rows": rows}


@router.get("/api/runs/{run_id}/accounts/{account_id}")
def account_file(run_id: UUID, account_id: str) -> dict:
    """One borrower's file: the findings for this audit and a UTC timeline of every record involved."""
    _run_or_404(run_id)
    fs = _all(f"""
        SELECT f.finding_id, f.check_id, c.question_ref, c.check_type, f.account_id, f.subject_ref, f.status, f.severity, f.reason,
               COALESCE(r.disposition, 'open') AS disposition, r.review_comment, r.reviewer,
               COALESCE((SELECT jsonb_agg(to_jsonb(ci) - 'finding_id' ORDER BY ci.citation_id)
                         FROM audit.citations ci WHERE ci.finding_id = f.finding_id), '[]') AS citations
        FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) {_LATEST_REVIEW}
        WHERE f.run_id = %s AND f.account_id = %s ORDER BY (f.status <> 'gap'), f.check_id, f.subject_ref NULLS FIRST""", (run_id, account_id))
    flag: dict[str, str] = {}
    prio = {"gap": 3, "cannot_determine": 2, "evidenced": 1}
    for f in fs:
        for c in f["citations"]:
            if prio[f["status"]] > prio.get(flag.get(c["record_key"], ""), 0):
                flag[c["record_key"]] = f["status"]
        if f["subject_ref"] and prio[f["status"]] > prio.get(flag.get(f["subject_ref"], ""), 0):
            flag[f["subject_ref"]] = f["status"]
    p = (account_id,)
    events: list[dict] = []
    def mask(no: str | None) -> str:
        return "" if not no else "X" * max(len(no) - 4, 0) + no[-4:]

    sessions = read_rows("SELECT * FROM staging.call_sessions WHERE account_id = %s", p)
    for r in sessions:
        note = ("; mirrored duplicate, counted under " + r["mirror_of"]) if r["is_mirror_duplicate"] else ""
        if r["direction"] != "OUTBOUND":
            note += "; inbound, not an attempt"
        events.append({"ts": r["started_ts_utc"], "kind": "call", "id": r["session_key"], "source": f"CN Core call log ({r['dialer_code']})",
                       "title": f"{r['direction'].title()} call ({', '.join(s.replace('_', ' ').lower() for s in r['statuses'])})",
                       "src_ts": r["started_ts_src"], "tz": r["started_ts_src_tz"],
                       "detail": f"To {mask(r['contact_no'])}; {(r['process_mode'] or '').lower()} mode; collector {r['employee_code'] or 'unknown'}{note}"})
    for r in read_rows("SELECT * FROM staging.messages WHERE account_id = %s", p):
        events.append({"ts": r["sent_ts_utc"], "kind": r["channel"].lower(), "id": r["message_id"], "source": "CN Core message log",
                       "title": f"{r['channel'].title()} message {r['status'].lower()}", "src_ts": r["sent_ts_src"], "tz": r["sent_ts_src_tz"],
                       "detail": f"To {mask(r['contact_no'])}; {(r['category'] or '').lower()} template {r['template_id']}"})
    for r in read_rows("SELECT c.* FROM staging.consents c WHERE c.customer_id = (SELECT customer_id FROM staging.accounts WHERE account_id = %s)", p):
        events.append({"ts": r["effective_ts_utc"], "kind": "consent", "id": r["consent_id"], "source": "Consent registry",
                       "title": f"Consent {r['status'].lower()} ({r['channel'].lower()}, {r['purpose'].lower()})", "src_ts": r["effective_ts_src"],
                       "tz": r["effective_ts_src_tz"], "detail": f"For {mask(r['contact_no'])}; captured via {r['capture_source']}"})
    keys = [r["session_key"] for r in sessions if r["connected"]]
    for r in (read_rows("SELECT * FROM staging.recordings WHERE session_key = ANY(%s)", (keys,)) if keys else []):
        sess = next(x for x in sessions if x["session_key"] == r["session_key"])
        events.append({"ts": sess["ended_ts_utc"] or sess["started_ts_utc"], "kind": "recording", "id": r["recording_id"], "source": "Recording store",
                       "title": f"Recording {r['storage_status'].replace('_', ' ').lower()}", "src_ts": r["checked_ts_src"], "tz": "checked",
                       "detail": f"Call {r['session_key']}" + (f"; {r['note']}" if r["note"] else "")})
    for r in read_rows("SELECT * FROM staging.notices WHERE account_id = %s", p):
        events.append({"ts": r["trigger_date"], "kind": "notice", "id": r["notice_id"], "source": "Notice dispatch history",
                       "title": f"{r['notice_type'].replace('_', ' ').title()}: triggered", "src_ts": str(r["trigger_date"]), "tz": "date",
                       "detail": f"Dispatched {r['dispatch_date'] or 'never'}; served {r['served_date'] or 'never'}", "all_day": True})
    for e in events:
        e["flag"] = flag.get(e["id"])
        e["ts"] = e["ts"].isoformat() if hasattr(e["ts"], "isoformat") else str(e["ts"])
    events.sort(key=lambda e: (e["ts"], e["id"]))
    acct = _one("SELECT account_number, institution_code FROM staging.accounts WHERE account_id = %s", (account_id,)) or {}
    return {"account_id": account_id, "account_number": acct.get("account_number"), "institution_code": acct.get("institution_code"),
            "findings": fs, "events": events}


