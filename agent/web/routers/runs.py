"""Engagements and their summaries, findings, reviews and management responses."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from agent.checks.catalog import CHECK_INFO
from agent.core.db import connect
from agent.services.pack import DISPOSITIONS
from agent.services.scoring import acceptance
from agent.services.traps import trap_counts
from agent.web.common import _LATEST_CHALLENGE, _LATEST_REVIEW, _all, _completed, _one, _run_or_404

router = APIRouter()


@router.get("/api/runs")
def list_runs() -> list[dict]:
    return _all("""
        SELECT r.run_id, r.request_id, r.lender, r.response_due, r.created_by, r.status, r.started_at, r.finished_at, r.notes,
               (SELECT count(*) FROM audit.checks c WHERE c.run_id = r.run_id) AS checks,
               count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
               count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
               count(f.*) FILTER (WHERE f.status = 'gap' AND r2.disposition IS NOT NULL AND r2.disposition <> 'open') AS gaps_reviewed,
               (SELECT count(DISTINCT account_id) FROM audit.sample_accounts s WHERE s.run_id = r.run_id) AS accounts,
               (SELECT status FROM audit.letters l WHERE l.run_id = r.run_id ORDER BY version DESC LIMIT 1) AS letter_status
        FROM audit.runs r
        LEFT JOIN audit.findings f USING (run_id)
        LEFT JOIN LATERAL (SELECT disposition FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id
                           ORDER BY x.review_id DESC LIMIT 1) r2 ON true
        WHERE r.kind = 'audit' GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 100""")


_COUNTS = """count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
             count(f.*) FILTER (WHERE f.status = 'gap') AS gap,
             count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine"""


@router.get("/api/runs/{run_id}")
def run_detail(run_id: UUID) -> dict:
    run = _run_or_404(run_id)
    checks = _all(f"""
        SELECT c.check_id, c.question_ref, c.question_text, c.check_type, c.sources, c.test_definition, c.sample_definition,
               (SELECT count(*) FROM audit.sample_accounts s WHERE s.run_id = c.run_id AND s.check_id = c.check_id) AS accounts,
               {_COUNTS}
        FROM audit.checks c LEFT JOIN audit.findings f USING (run_id, check_id)
        WHERE c.run_id = %s GROUP BY c.run_id, c.check_id ORDER BY c.check_id""", (run_id,))
    per_acct = {r["check_id"]: r for r in _all("""
        SELECT check_id, count(*) AS accounts_tested, count(*) FILTER (WHERE g) AS accounts_gap,
               count(*) FILTER (WHERE NOT g AND e) AS accounts_ok, count(*) FILTER (WHERE NOT g AND NOT e) AS accounts_unknown
        FROM (SELECT check_id, account_id, bool_or(status = 'gap') AS g, bool_or(status = 'evidenced') AS e
              FROM audit.findings WHERE run_id = %s GROUP BY check_id, account_id) t GROUP BY check_id""", (run_id,))}
    for c in checks:
        c.update(per_acct.get(c["check_id"], {"accounts_tested": 0, "accounts_gap": 0, "accounts_ok": 0, "accounts_unknown": 0}))
        c["title"] = CHECK_INFO[c["check_type"]]["title"]
    scale = list(run["severity_scale"])
    severity = _all("""SELECT severity, count(*) AS findings, count(DISTINCT account_id) AS accounts
                       FROM audit.findings WHERE run_id = %s AND status = 'gap' GROUP BY severity""", (run_id,))
    severity.sort(key=lambda s: scale.index(s["severity"]) if s["severity"] in scale else len(scale))
    totals = _one(f"""SELECT {_COUNTS}, count(DISTINCT f.account_id) FILTER (WHERE f.status = 'gap') AS accounts_with_gaps
                      FROM audit.findings f WHERE f.run_id = %s""", (run_id,))
    sample = _one("SELECT count(DISTINCT account_id) AS n FROM audit.sample_accounts WHERE run_id = %s", (run_id,))["n"]
    no_data = _all("""SELECT s.account_id FROM (SELECT DISTINCT account_id FROM audit.sample_accounts WHERE run_id = %s) s
                      WHERE NOT EXISTS (SELECT 1 FROM staging.call_sessions c WHERE c.account_id = s.account_id)
                        AND NOT EXISTS (SELECT 1 FROM staging.messages m WHERE m.account_id = s.account_id)
                      ORDER BY 1 LIMIT 50""", (run_id,))
    refs = _all("""SELECT original_ref, match_status, candidates, note FROM audit.sample_references
                   WHERE run_id = %s AND match_status <> 'matched' ORDER BY match_status, original_ref""", (run_id,))
    total_refs = _one("SELECT count(*) AS n FROM audit.sample_references WHERE run_id = %s", (run_id,))["n"]
    collectors = _all("""
        SELECT COALESCE(c.employee_code, 'user ' || c.collector_user_id) AS collector_id, k.agency, count(*) AS gaps,
               count(DISTINCT f.account_id) AS accounts, array_agg(DISTINCT ck.question_ref ORDER BY ck.question_ref) AS questions
        FROM audit.findings f JOIN audit.checks ck USING (run_id, check_id)
        JOIN staging.call_sessions c ON c.session_key = f.subject_ref
        LEFT JOIN staging.collectors k ON k.user_id = c.collector_user_id::text
        WHERE f.run_id = %s AND f.status = 'gap'
        GROUP BY COALESCE(c.employee_code, 'user ' || c.collector_user_id), k.agency ORDER BY gaps DESC, 1 LIMIT 8""", (run_id,))
    months = _all("""
        SELECT month, count(*) AS gaps FROM (
            SELECT to_char(date_trunc('month', c.started_ts_utc AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM') AS month
            FROM audit.findings f JOIN staging.call_sessions c ON c.session_key = f.subject_ref WHERE f.run_id = %s AND f.status = 'gap'
            UNION ALL
            SELECT to_char(date_trunc('month', m.sent_ts_utc AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM')
            FROM audit.findings f JOIN staging.messages m ON m.message_id = f.subject_ref WHERE f.run_id = %s AND f.status = 'gap') t
        GROUP BY month ORDER BY month""", (run_id, run_id))
    review = _all(f"""SELECT f.status, COALESCE(r.disposition, 'open') AS disposition, count(*) AS n
                      FROM audit.findings f {_LATEST_REVIEW} WHERE f.run_id = %s AND f.status IN ('gap', 'cannot_determine')
                      GROUP BY 1, 2""", (run_id,))
    letter = _one("SELECT version, status, author, created_at FROM audit.letters WHERE run_id = %s ORDER BY version DESC LIMIT 1", (run_id,))
    responses = _one("SELECT count(DISTINCT question_ref) AS n FROM audit.question_responses WHERE run_id = %s", (run_id,))["n"]
    challenges = {r["verdict"]: r["n"] for r in _all("""SELECT y.verdict, count(*) AS n FROM (SELECT DISTINCT ON (finding_id) finding_id, verdict FROM audit.finding_challenges
                      WHERE run_id = %s ORDER BY finding_id, challenge_id DESC) y GROUP BY y.verdict""", (run_id,))}
    return {"run": run, "checks": checks, "severity": severity, "totals": totals, "challenges": challenges, "acceptance": acceptance(run_id),
            "tested_checks": sum(1 for c in checks if c["accounts_tested"] > 0),
            "coverage": {"sampled": sample, "no_data": [r["account_id"] for r in no_data], "references": total_refs,
                         "unresolved": [{"ref": r["original_ref"], "status": r["match_status"], "candidates": r["candidates"], "note": r["note"]} for r in refs]},
            "collectors": collectors, "months": months, "review": review, "letter": letter,
            "responses": responses, "questions": len({c["question_ref"] for c in checks})}


@router.get("/api/runs/{run_id}/findings")
def findings(run_id: UUID, check_id: str | None = None, question: str | None = None, status: str | None = None,
             account: str | None = None, severity: str | None = None, disposition: str | None = None, challenge: str | None = None, text: str | None = None,
             limit: int = 50, offset: int = 0) -> dict:
    run = _run_or_404(run_id)
    where, params = ["f.run_id = %s"], [run_id]
    for col, val in (("f.check_id", check_id), ("c.question_ref", question), ("f.status", status), ("f.severity", severity)):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    if disposition:
        where.append("COALESCE(r.disposition, 'open') = %s")
        params.append(disposition)
    if text:
        where.append("f.reason ILIKE %s")
        params.append(f"%{text.strip()}%")
    if challenge == "flagged":
        where.append("ch.challenge_verdict IN ('disputes', 'unclear')")
    if account:
        where.append("(f.account_id ILIKE %s OR a.account_number ILIKE %s)")
        params += [f"%{account.strip()}%"] * 2
    clause = " AND ".join(where)
    base = (f"FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) LEFT JOIN staging.accounts a ON a.account_id = f.account_id "
            f"{_LATEST_REVIEW} {_LATEST_CHALLENGE} WHERE {clause}")
    total = _one(f"SELECT count(*) AS n {base}", tuple(params))["n"]
    rows = _all(f"""
        SELECT f.finding_id, f.check_id, c.question_ref, c.check_type, f.account_id, a.account_number, f.subject_ref, f.status, f.severity,
               f.reason, f.evidence_query, ch.challenge_verdict, ch.challenge_concern, COALESCE(r.disposition, 'open') AS disposition, r.review_comment, r.reviewer, r.reviewed_at,
               COALESCE((c.test_definition->>'priority_weight')::int, 1) AS priority_weight,
               COALESCE((SELECT jsonb_agg(to_jsonb(ci) - 'finding_id' ORDER BY ci.citation_id)
                         FROM audit.citations ci WHERE ci.finding_id = f.finding_id), '[]') AS citations
        {base}
        ORDER BY (f.status <> 'gap'), (COALESCE(ch.challenge_verdict, 'supports') = 'supports'), COALESCE(array_position(%s::text[], f.severity), 99),
                 -COALESCE((c.test_definition->>'priority_weight')::int, 1), f.check_id, f.account_id,
                 f.subject_ref NULLS FIRST
        LIMIT %s OFFSET %s""", (*params, list(run["severity_scale"]), max(1, min(limit, 500)), max(0, offset)))
    return {"total": total, "rows": rows}


@router.post("/api/runs/{run_id}/reviews")
async def add_reviews(run_id: UUID, request: Request) -> dict:
    """Record a reviewer's decision on one or more findings. Adds rows; never edits or removes a finding."""
    _completed(run_id)
    body = await request.json()
    ids, disp = [int(i) for i in body.get("finding_ids", [])], body.get("disposition")
    reviewer, comment = str(body.get("reviewer", "")).strip(), str(body.get("comment", "")).strip()
    if not ids:
        raise HTTPException(400, "Select at least one finding.")
    if disp not in DISPOSITIONS:
        raise HTTPException(400, "Unknown review decision.")
    if not reviewer:
        raise HTTPException(400, "Enter your name before reviewing, so the decision can be attributed.")
    if disp in ("disputed", "remediation_planned") and not comment:
        raise HTTPException(400, "A comment is required when disputing a gap or planning remediation.")
    with connect() as conn, conn.transaction():
        found = {r["finding_id"] for r in conn.execute(
            "SELECT finding_id FROM audit.findings WHERE run_id = %s AND finding_id = ANY(%s)", (run_id, ids))}
        if found != set(ids):
            raise HTTPException(400, "Some findings do not belong to this audit.")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO audit.finding_reviews (run_id, finding_id, reviewer, disposition, comment) VALUES (%s, %s, %s, %s, %s)",
                            [(run_id, i, reviewer, disp, comment or None) for i in ids])
    return {"saved": len(ids)}


@router.get("/api/runs/{run_id}/responses")
def responses(run_id: UUID) -> dict:
    _run_or_404(run_id)
    return {r["question_ref"]: r for r in _all(
        "SELECT DISTINCT ON (question_ref) question_ref, body, author, created_at FROM audit.question_responses "
        "WHERE run_id = %s ORDER BY question_ref, response_id DESC", (run_id,))}


@router.put("/api/runs/{run_id}/responses/{question_ref}")
async def put_response(run_id: UUID, question_ref: str, request: Request) -> dict:
    _completed(run_id)
    body = await request.json()
    text, author = str(body.get("body", "")).strip(), str(body.get("author", "")).strip()
    if not author:
        raise HTTPException(400, "Enter your name first.")
    if not text:
        raise HTTPException(400, "Write the management comment first.")
    with connect() as conn:
        conn.execute("INSERT INTO audit.question_responses (run_id, question_ref, author, body) VALUES (%s, %s, %s, %s)",
                     (run_id, question_ref, author, text))
    return {"saved": True}




@router.get("/api/runs/{run_id}/traps")
def run_traps(run_id: UUID) -> list[dict]:
    """The subtle evidence traps this audit caught, counted from its findings."""
    _run_or_404(run_id)
    return trap_counts(run_id)
