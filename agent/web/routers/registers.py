"""The registers a team works from across audits: exceptions (every reported gap and open question), issues (gaps tracked to closure),
the audit plan, the risk matrix and alerts. Reads here; changes go through agent.services."""
from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from agent.services import issues, plan, risk
from agent.web.common import _LATEST_CHALLENGE, _LATEST_REVIEW, _all, _one, cached
from agent.web.routers.dashboard import dashboard

router = APIRouter()


def _day(v) -> date | None:
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        raise HTTPException(400, "Dates must look like 2026-12-31.")


# ---------------------------------------------------------------- exceptions: every gap and open question, across audits

_OPEN_ISSUE = """(SELECT i.issue_id FROM audit.issue_findings l JOIN audit.issues i USING (issue_id)
                  WHERE l.finding_id = f.finding_id AND i.status NOT IN ('verified', 'wont_fix') ORDER BY i.issue_id DESC LIMIT 1)"""


def _exception_filters(status, severity, check_type, run, disposition, issue, text, account, challenge) -> tuple[str, list]:
    where, params = ["ru.status = 'completed'", "ru.kind = 'audit'", "f.status IN ('gap', 'cannot_determine')"], []
    for sql, val in (("f.status = %s", status), ("f.severity = %s", severity), ("c.check_type = %s", check_type), ("f.run_id::text = %s", run)):
        if val:
            where.append(sql)
            params.append(val)
    if disposition:
        where.append("COALESCE(r.disposition, 'open') = %s")
        params.append(disposition)
    if issue == "none":
        where.append(f"{_OPEN_ISSUE} IS NULL")
    elif issue == "open":
        where.append(f"{_OPEN_ISSUE} IS NOT NULL")
    if challenge == "flagged":
        where.append("ch.challenge_verdict IN ('disputes', 'unclear')")
    if text:
        where.append("f.reason ILIKE %s")
        params.append(f"%{text.strip()}%")
    if account:
        where.append("(f.account_id ILIKE %s OR a.account_number ILIKE %s)")
        params += [f"%{account.strip()}%"] * 2
    return " AND ".join(where), params


_EXC_FROM = f"""FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) JOIN audit.runs ru USING (run_id)
                LEFT JOIN staging.accounts a ON a.account_id = f.account_id {_LATEST_REVIEW} {_LATEST_CHALLENGE}"""
_EXC_ORDER = """ORDER BY (f.status <> 'gap'), (COALESCE(ch.challenge_verdict, 'supports') = 'supports'),
                COALESCE((SELECT t.ord FROM jsonb_array_elements_text(ru.severity_scale) WITH ORDINALITY t(v, ord) WHERE t.v = f.severity), 99), f.finding_id DESC"""


@router.get("/api/exceptions")
def exceptions(status: str = "", severity: str = "", check_type: str = "", run: str = "", disposition: str = "", issue: str = "", text: str = "",
               account: str = "", challenge: str = "", limit: int = 50, offset: int = 0) -> dict:
    where, params = _exception_filters(status, severity, check_type, run, disposition, issue, text, account, challenge)
    total = _one(f"SELECT count(*) AS n {_EXC_FROM} WHERE {where}", tuple(params))["n"]
    rows = _all(f"""SELECT f.finding_id, f.run_id, ru.request_id, c.question_ref, c.check_type, f.account_id, a.account_number, f.subject_ref, f.status, f.severity,
                           left(f.reason, 320) AS reason, COALESCE(r.disposition, 'open') AS disposition, ch.challenge_verdict, {_OPEN_ISSUE} AS issue_id
                    {_EXC_FROM} WHERE {where} {_EXC_ORDER} LIMIT %s OFFSET %s""", (*params, max(1, min(limit, 200)), max(0, offset)))
    facets = _all("""SELECT c.check_type, count(*) AS n FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) JOIN audit.runs ru USING (run_id)
                     WHERE ru.status = 'completed' AND ru.kind = 'audit' AND f.status IN ('gap', 'cannot_determine') GROUP BY 1 ORDER BY 2 DESC""")
    runs = _all("SELECT run_id, request_id FROM audit.runs WHERE status = 'completed' AND kind = 'audit' ORDER BY started_at DESC LIMIT 50")
    return {"total": total, "rows": rows, "check_types": facets, "runs": runs}


@router.get("/api/exceptions.csv")
def exceptions_csv(status: str = "", severity: str = "", check_type: str = "", run: str = "", disposition: str = "", issue: str = "", text: str = "",
                   account: str = "", challenge: str = "") -> Response:
    where, params = _exception_filters(status, severity, check_type, run, disposition, issue, text, account, challenge)
    rows = _all(f"""SELECT ru.request_id, f.finding_id, c.question_ref, c.check_type, a.account_number, f.account_id, f.subject_ref, f.status, f.severity, f.reason,
                           COALESCE(r.disposition, 'open') AS review, ch.challenge_verdict AS second_reading, {_OPEN_ISSUE} AS issue_id
                    {_EXC_FROM} WHERE {where} {_EXC_ORDER} LIMIT 20000""", tuple(params))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["audit", "finding_id", "question", "test", "loan_account", "cn_account_id", "event", "status", "severity", "reason", "review", "second_reading", "issue_id"])
    for r in rows:
        w.writerow([r["request_id"], r["finding_id"], r["question_ref"], r["check_type"], r["account_number"] or "", r["account_id"], r["subject_ref"] or "", r["status"],
                    r["severity"] or "", r["reason"], r["review"], r["second_reading"] or "", r["issue_id"] or ""])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="exceptions.csv"'})


# ---------------------------------------------------------------- issues

def _issue_rows(where: str = "TRUE", params: tuple = ()) -> list[dict]:
    return _all(f"""SELECT i.issue_id, i.title, i.check_type, i.severity, i.owner, i.due_date, i.status, i.created_by, i.created_at,
                           (SELECT count(*) FROM audit.issue_findings l WHERE l.issue_id = i.issue_id) AS findings,
                           (i.due_date IS NOT NULL AND i.due_date < CURRENT_DATE AND i.status NOT IN ('verified', 'wont_fix')) AS overdue
                    FROM audit.issues i WHERE {where} ORDER BY (i.status IN ('verified', 'wont_fix')), i.due_date NULLS LAST, i.issue_id DESC LIMIT 500""", params)


@router.get("/api/issues")
def issue_list(status: str = "", owner: str = "", overdue: bool = False) -> dict:
    where, params = ["TRUE"], []
    if status == "active":
        where.append("i.status NOT IN ('verified', 'wont_fix')")
    elif status:
        where.append("i.status = %s")
        params.append(status)
    if owner:
        where.append("i.owner ILIKE %s")
        params.append(f"%{owner.strip()}%")
    if overdue:
        where.append("i.due_date < CURRENT_DATE AND i.status NOT IN ('verified', 'wont_fix')")
    counts = {r["status"]: r["n"] for r in _all("SELECT status, count(*) AS n FROM audit.issues GROUP BY status")}
    return {"rows": _issue_rows(" AND ".join(where), tuple(params)), "counts": counts, "transitions": {k: list(v) for k, v in issues.TRANSITIONS.items()}}


@router.get("/api/issues.csv")
def issues_csv() -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["issue_id", "title", "test", "severity", "owner", "due_date", "status", "gaps", "raised_by", "raised_at"])
    for r in _issue_rows():
        w.writerow([r["issue_id"], r["title"], r["check_type"] or "", r["severity"] or "", r["owner"] or "", r["due_date"] or "", r["status"], r["findings"], r["created_by"], r["created_at"]])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="issues.csv"'})


@router.get("/api/issues/{issue_id}")
def issue_detail(issue_id: int) -> dict:
    row = next(iter(_issue_rows("i.issue_id = %s", (issue_id,))), None)
    if not row:
        raise HTTPException(404, "No such issue")
    gaps = _all("""SELECT f.finding_id, f.run_id, ru.request_id, c.question_ref, c.check_type, f.account_id, a.account_number, f.status, f.severity, f.reason
                   FROM audit.issue_findings l JOIN audit.findings f USING (finding_id) JOIN audit.checks c USING (run_id, check_id) JOIN audit.runs ru USING (run_id)
                   LEFT JOIN staging.accounts a ON a.account_id = f.account_id WHERE l.issue_id = %s ORDER BY f.finding_id LIMIT 200""", (issue_id,))
    events = _all("SELECT actor, kind, body, created_at FROM audit.issue_events WHERE issue_id = %s ORDER BY event_id", (issue_id,))
    description = _one("SELECT description FROM audit.issues WHERE issue_id = %s", (issue_id,))["description"]
    return {**row, "description": description, "gaps": gaps, "events": events, "next_statuses": list(issues.TRANSITIONS[row["status"]])}


@router.post("/api/issues")
async def issue_create(request: Request) -> dict:
    b = await request.json()
    actor = str(b.get("actor", "")).strip()
    if not actor:
        raise HTTPException(400, "Enter your name first.")
    try:
        return {"issue_id": issues.create([int(i) for i in b.get("finding_ids", [])], str(b.get("title", "")), str(b.get("owner", "")).strip() or None, _day(b.get("due")),
                                          str(b.get("description", "")).strip() or None, actor)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/issues/{issue_id}")
async def issue_update(issue_id: int, request: Request) -> dict:
    b = await request.json()
    actor = str(b.get("actor", "")).strip()
    if not actor:
        raise HTTPException(400, "Enter your name first.")
    try:
        issues.update(issue_id, actor, status=b.get("status") or None, owner=b.get("owner"), due=_day(b.get("due")), note=b.get("note"))
    except LookupError:
        raise HTTPException(404, "No such issue")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


# ---------------------------------------------------------------- the audit plan

@router.get("/api/plan")
def plan_list() -> dict:
    rows = _all("""SELECT p.plan_id, p.title, p.lender, p.scope, p.kind, p.planned_start, p.due_date, p.owner, p.recurrence, p.status, p.run_id, p.created_by,
                          r.request_id, r.status AS run_status,
                          (p.due_date IS NOT NULL AND p.due_date < CURRENT_DATE AND p.status IN ('planned', 'in_progress')) AS overdue
                   FROM audit.audit_plan p LEFT JOIN audit.runs r USING (run_id)
                   ORDER BY (p.status IN ('done', 'cancelled')), COALESCE(p.due_date, p.planned_start) NULLS LAST, p.plan_id""")
    return {"rows": rows}


@router.post("/api/plan")
async def plan_create(request: Request) -> dict:
    b = await request.json()
    actor = str(b.get("actor", "")).strip()
    if not actor:
        raise HTTPException(400, "Enter your name first.")
    try:
        return {"plan_id": plan.create(str(b.get("title", "")), str(b.get("lender", "")).strip() or None, str(b.get("scope", "")).strip() or None, str(b.get("kind", "audit")),
                                       _day(b.get("planned_start")), _day(b.get("due_date")), str(b.get("owner", "")).strip() or None, str(b.get("recurrence", "none")), actor)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/plan/{plan_id}/status")
async def plan_status(plan_id: int, request: Request) -> dict:
    b = await request.json()
    try:
        plan.set_status(plan_id, str(b.get("status", "")))
    except LookupError:
        raise HTTPException(404, "No such plan entry")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


# ---------------------------------------------------------------- risk and alerts

@router.get("/api/risk")
@cached(120)
def risk_matrix() -> dict:
    return risk.assess()


@router.get("/api/alerts")
def alerts() -> dict:
    """What needs a person, most urgent first: the dashboard's attention items, overdue and soon-due issues, and planned audits that are due."""
    items = [{**a, "kind": "audit"} for a in dashboard()["attention"]]
    for i in _all("""SELECT issue_id, title, owner, due_date, (due_date < CURRENT_DATE) AS late FROM audit.issues
                     WHERE status NOT IN ('verified', 'wont_fix') AND due_date IS NOT NULL AND due_date <= CURRENT_DATE + 7 ORDER BY due_date LIMIT 20"""):
        items.append({"level": "critical" if i["late"] else "warning", "run": f"Issue #{i['issue_id']}", "kind": "issue", "link": f"#/issues/{i['issue_id']}",
                      "text": f"{i['title']}: {'was due' if i['late'] else 'is due'} {i['due_date']}{' (' + i['owner'] + ')' if i['owner'] else ' (no owner)'}."})
    for p in _all("""SELECT plan_id, title, due_date, (due_date < CURRENT_DATE) AS late FROM audit.audit_plan
                     WHERE status IN ('planned', 'in_progress') AND due_date IS NOT NULL AND due_date <= CURRENT_DATE + 14 ORDER BY due_date LIMIT 20"""):
        items.append({"level": "critical" if p["late"] else "warning", "run": "Audit plan", "kind": "plan", "link": "#/plan",
                      "text": f"{p['title']}: {'was due' if p['late'] else 'is due'} {p['due_date']}."})
    order = {"critical": 0, "warning": 1}
    items.sort(key=lambda a: order[a["level"]])
    return {"items": items, "count": len(items), "critical": sum(a["level"] == "critical" for a in items)}
