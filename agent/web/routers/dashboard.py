"""The dashboard: how every audit stands, and what needs attention first. Read-only, from audit.* and the staging views."""
from __future__ import annotations

import threading
import time
from datetime import date

from fastapi import APIRouter, HTTPException, Request

from agent.services import readiness
from agent.services.audit import process
from agent.services.scoring import acceptance
from agent.services.traps import trap_counts
from agent.web.common import _LATEST_CHALLENGE, _LATEST_REVIEW, _RUN_LOCK, _all, _one

router = APIRouter()

SLA_SECONDS = 2 * 3600  # the target: 300 accounts and 10 questions in under two hours


_cache: dict = {"at": 0.0, "value": None}


@router.get("/api/dashboard")
def dashboard() -> dict:
    """Cached for two minutes (and warmed when the server starts): the page is opened often and the figures change at the pace of an audit."""
    if _cache["value"] is None or time.monotonic() - _cache["at"] > 120:
        _cache.update(at=time.monotonic(), value=_dashboard())
    return _cache["value"]


def _dashboard() -> dict:
    runs = _one("""SELECT count(*) AS total, count(*) FILTER (WHERE status = 'completed') AS completed, count(*) FILTER (WHERE status = 'running') AS running,
                          count(*) FILTER (WHERE status = 'failed') AS failed FROM audit.runs WHERE kind = 'audit'""")
    totals = _one("""SELECT count(*) FILTER (WHERE f.status = 'evidenced') AS evidenced, count(*) FILTER (WHERE f.status = 'gap') AS gaps,
                            count(*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
                            count(DISTINCT (f.run_id, f.account_id)) AS accounts_tested,
                            count(*) FILTER (WHERE f.status = 'gap' AND COALESCE(r.disposition, 'open') <> 'open') AS gaps_reviewed,
                            count(*) FILTER (WHERE f.status = 'gap' AND ch.challenge_verdict IN ('disputes', 'unclear')) AS skeptic_flagged,
                            count(*) FILTER (WHERE f.status = 'gap' AND ch.challenge_verdict IS NOT NULL) AS skeptic_read
                     FROM audit.findings f JOIN audit.runs ru USING (run_id) {rv} {ch} WHERE ru.status = 'completed' AND ru.kind = 'audit'""".format(rv=_LATEST_REVIEW, ch=_LATEST_CHALLENGE))
    letters = _one("""SELECT count(*) FILTER (WHERE l.status = 'approved') AS approved, count(*) AS runs_with_letter
                      FROM (SELECT DISTINCT ON (run_id) run_id, status FROM audit.letters ORDER BY run_id, version DESC) l""")
    severity = _all("""SELECT f.severity, min(COALESCE((SELECT t.ord FROM jsonb_array_elements_text(ru.severity_scale) WITH ORDINALITY t(v, ord) WHERE t.v = f.severity), 99)) AS rank, count(*) AS n
                       FROM audit.findings f JOIN audit.runs ru USING (run_id) WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status = 'gap'
                       GROUP BY f.severity ORDER BY rank, f.severity""")
    by_check = _all("""SELECT c.check_type, count(*) FILTER (WHERE f.status = 'evidenced') AS evidenced, count(*) FILTER (WHERE f.status = 'gap') AS gaps,
                              count(*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine
                       FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) JOIN audit.runs ru USING (run_id)
                       WHERE ru.status = 'completed' GROUP BY c.check_type ORDER BY gaps DESC, c.check_type""")
    months = _all("""
        SELECT month, count(*) AS gaps FROM (
            SELECT to_char(date_trunc('month', c.started_ts_utc AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM') AS month
            FROM audit.findings f JOIN audit.runs ru USING (run_id) JOIN staging.call_sessions c ON c.session_key = f.subject_ref
            WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status = 'gap'
            UNION ALL
            SELECT to_char(date_trunc('month', m.sent_ts_utc AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM')
            FROM audit.findings f JOIN audit.runs ru USING (run_id) JOIN staging.messages m ON m.message_id = f.subject_ref
            WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status = 'gap') t
        GROUP BY month ORDER BY month""")
    agencies = _all("""
        SELECT COALESCE(k.agency, 'Unknown agency') AS agency, count(*) AS gaps, count(DISTINCT c.collector_user_id) AS collectors
        FROM audit.findings f JOIN audit.runs ru USING (run_id) JOIN staging.call_sessions c ON c.session_key = f.subject_ref
        LEFT JOIN staging.collectors k ON k.user_id = c.collector_user_id::text
        WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status = 'gap' GROUP BY 1 ORDER BY gaps DESC, 1 LIMIT 8""")
    agent = _one("""SELECT count(*) AS steps, count(*) FILTER (WHERE phase = 'investigate' AND status = 'resolved') AS found_elsewhere,
                           count(*) FILTER (WHERE status = 'failed') AS failed_steps FROM audit.agent_steps""")
    recent = _all("""
        SELECT r.run_id, r.request_id, r.lender, r.status, r.started_at, r.response_due, EXTRACT(EPOCH FROM (r.finished_at - r.started_at))::int AS seconds,
               (SELECT count(DISTINCT account_id) FROM audit.sample_accounts s WHERE s.run_id = r.run_id) AS accounts,
               (SELECT count(*) FROM audit.checks c WHERE c.run_id = r.run_id) AS checks,
               count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'gap' AND COALESCE(rv.disposition, 'open') = 'open' AND f.severity = r.severity_scale->>0) AS open_top,
               count(f.*) FILTER (WHERE f.status = 'gap' AND ch.challenge_verdict IN ('disputes', 'unclear') AND COALESCE(rv.disposition, 'open') = 'open') AS flagged_open,
               (SELECT status FROM audit.letters l WHERE l.run_id = r.run_id ORDER BY version DESC LIMIT 1) AS letter_status,
               (SELECT count(*) FROM audit.sample_references sr WHERE sr.run_id = r.run_id AND sr.match_status <> 'matched') AS unresolved_refs
        FROM audit.runs r LEFT JOIN audit.findings f USING (run_id)
        LEFT JOIN LATERAL (SELECT disposition FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id ORDER BY x.review_id DESC LIMIT 1) rv ON true
        {ch}
        WHERE r.kind = 'audit' GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 12""".format(ch=_LATEST_CHALLENGE))

    # the audit the headline figures describe: the latest one scored against an answer key, else the latest completed
    scored = _one("SELECT s.run_id FROM audit.run_scores s JOIN audit.runs r USING (run_id) WHERE r.kind = 'audit' AND r.status = 'completed' ORDER BY s.score_id DESC LIMIT 1")
    focus = next((r for r in recent if scored and r["run_id"] == scored["run_id"]), None) or next((r for r in recent if r["status"] == "completed"), None)
    today, attention = date.today(), []
    for r in recent:
        link = f"#/run/{r['run_id']}"
        if r["status"] == "failed":
            attention.append({"level": "critical", "run": r["request_id"], "text": "The audit stopped before it finished.", "link": link})
            continue
        if r["status"] != "completed":
            continue
        due = r["response_due"]
        if r["letter_status"] != "approved" and due:
            days = (due - today).days
            if days < 0:
                attention.append({"level": "critical", "run": r["request_id"], "text": f"Response was due {-days} day(s) ago and the letter is not approved.", "link": f"{link}/letter"})
            elif days <= 7:
                attention.append({"level": "warning", "run": r["request_id"], "text": f"Response due in {days} day(s); the letter is {(r['letter_status'] or 'not started').replace('_', ' ')}.", "link": f"{link}/letter"})
        if r["open_top"]:
            attention.append({"level": "critical", "run": r["request_id"], "text": f"{r['open_top']} gap(s) at the top severity are still unreviewed.", "link": f"{link}/gaps"})
        if r["flagged_open"]:
            attention.append({"level": "warning", "run": r["request_id"], "text": f"The second reading disagrees with, or cannot confirm, {r['flagged_open']} unreviewed gap(s). Review these first.", "link": f"{link}/gaps?challenge=flagged"})
        if r["unresolved_refs"]:
            attention.append({"level": "warning", "run": r["request_id"], "text": f"{r['unresolved_refs']} account reference(s) were not tested (unmatched or ambiguous).", "link": f"{link}/accounts"})
    order = {"critical": 0, "warning": 1}
    attention.sort(key=lambda a: order[a["level"]])
    return {"runs": runs, "totals": totals, "letters": letters, "severity": severity, "by_check": by_check, "months": months, "agencies": agencies,
            "agent": agent, "recent": recent, "attention": attention[:12], "sla_seconds": SLA_SECONDS,
            "traps": trap_counts(), "acceptance": acceptance(focus["run_id"]) if focus else None,
            "latest_run": {"run_id": str(focus["run_id"]), "request_id": focus["request_id"], "seconds": focus["seconds"], "accounts": focus["accounts"], "checks": focus["checks"]} if focus else None,
            "forecast": readiness.forecast(), "readiness": _readiness_state()}


def _readiness_state() -> dict:
    """The latest readiness check: running, finished, or none yet."""
    row = _one("SELECT run_id, status, started_at, finished_at, (SELECT count(DISTINCT account_id) FROM audit.sample_accounts s WHERE s.run_id = r.run_id) AS accounts "
               "FROM audit.runs r WHERE kind = 'readiness' ORDER BY started_at DESC LIMIT 1")
    return {"run_id": str(row["run_id"]), "status": row["status"], "started_at": row["started_at"], "finished_at": row["finished_at"], "accounts": row["accounts"]} if row else {}


@router.post("/api/readiness")
async def start_readiness(request: Request) -> dict:
    """Start a readiness check: the same audit, on a random sample, before any auditor asks."""
    body = await request.json()
    who = str(body.get("requested_by", "")).strip()
    if not who:
        raise HTTPException(400, "Enter your name first.")
    if _readiness_state().get("status") == "running":
        raise HTTPException(409, "A readiness check is already running.")
    size = max(50, min(int(body.get("size", readiness.DEFAULT_SIZE)), 2000))
    run_id, req, period = readiness.start(size, who)

    def work() -> None:
        with _RUN_LOCK:
            try:
                process(run_id, req, log=lambda _: None, period=period, size=size)
            except Exception:
                pass  # recorded on the run

    threading.Thread(target=work, daemon=True).start()
    _cache["value"] = None
    return {"run_id": str(run_id), "size": size}


def warm() -> None:
    """Build the dashboard once in the background when the server starts, so the first person to open it does not wait."""
    threading.Thread(target=lambda: _safe(dashboard), daemon=True).start()


def _safe(fn) -> None:
    try:
        fn()
    except Exception:
        pass  # the dashboard is built again, and its error shown, when someone opens it
