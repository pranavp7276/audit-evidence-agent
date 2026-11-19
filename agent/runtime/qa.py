""""Ask the audit": a small agent that answers an auditor's question about one run from that run's own findings.

It follows a bounded loop: the reasoning model picks one read-only query tool, sees what came back, and either asks for another or
answers, for at most MAX_STEPS steps. The answer must name the finding ids it rests on, and an id the tools did not return is
rejected, so the agent cannot cite a finding that does not exist. With no model available, a deterministic answer built from the
same queries is returned instead. It reads findings; it never writes, re-tests or changes a result.  Finding reasons already mask phone
numbers; no borrower name or contact detail is queried.
"""
from __future__ import annotations

import re
from uuid import UUID

from agent.core import llm
from agent.core.db import read_rows
from agent.core.trace import Trace

MAX_STEPS = 4
MAX_ROWS = 15
_STATUSES = ("evidenced", "gap", "cannot_determine")

_MENU = """Tools (reply with one JSON object):
 {"action":"tool","tool":"summary"}                                    counts per check and status
 {"action":"tool","tool":"count","args":{"check_id":"Q1","status":"gap","severity":"Critical"}}   any filter optional
 {"action":"tool","tool":"list","args":{"check_id":"Q1","status":"gap","severity":"High","account_id":"...","limit":10}}   findings with ids
 {"action":"tool","tool":"top_accounts","args":{"limit":5}}            accounts with the most gaps
To finish: {"action":"answer","answer":"<plain sentences>","finding_ids":[<ids you rely on>]}"""


def _where(args: dict) -> tuple[str, list]:
    cond, params = ["f.run_id = %s"], []
    for col, key in (("f.check_id", "check_id"), ("f.status", "status"), ("f.severity", "severity"), ("f.account_id", "account_id")):
        if args.get(key):
            cond.append(f"{col} = %s")
            params.append(str(args[key]))
    return " AND ".join(cond), params


def _run_tool(run_id: UUID, name: str, args: dict) -> tuple[list[dict], list[int]]:
    """Execute one query tool; returns its rows and the finding ids they carry."""
    where, params = _where(args if isinstance(args, dict) else {})
    base = (run_id, *params)
    if name == "summary":
        rows = read_rows("SELECT check_id, status, count(*) AS n FROM audit.findings f WHERE f.run_id = %s GROUP BY check_id, status ORDER BY check_id, status", (run_id,))
        return rows, []
    if name == "count":
        return read_rows(f"SELECT status, severity, count(*) AS n FROM audit.findings f WHERE {where} GROUP BY status, severity ORDER BY n DESC", base), []
    if name == "list":
        limit = max(1, min(int(args.get("limit", 10)), MAX_ROWS)) if isinstance(args, dict) else 10
        rows = read_rows(f"SELECT f.finding_id, f.check_id, f.account_id, f.status, f.severity, left(f.reason, 220) AS reason FROM audit.findings f WHERE {where} "
                         f"ORDER BY (f.status = 'gap') DESC, f.finding_id LIMIT {limit}", base)
        return rows, [r["finding_id"] for r in rows]
    if name == "top_accounts":
        limit = max(1, min(int(args.get("limit", 5)), MAX_ROWS)) if isinstance(args, dict) else 5
        return read_rows("SELECT f.account_id, count(*) AS gaps, min(f.finding_id) AS example_finding_id FROM audit.findings f WHERE f.run_id = %s AND f.status = 'gap' "
                         f"GROUP BY f.account_id ORDER BY gaps DESC, f.account_id LIMIT {limit}", (run_id,)), []
    raise ValueError(f"unknown tool {name!r}")


def _fallback(run_id: UUID, question: str, trace: Trace) -> dict:
    """No model: answer from the same queries, guided by words in the question."""
    q = question.lower()
    args: dict = {}
    if m := re.search(r"\bq\d+[a-z]?\b", q):
        args["check_id"] = m.group(0).upper()
    for s in _STATUSES:
        if s.replace("_", " ") in q or (s == "gap" and "gaps" in q):
            args["status"] = s
    for sev in ("critical", "high", "medium", "low"):
        if sev in q:
            args["severity"] = sev.title()
    rows, ids = _run_tool(run_id, "list", {**args, "limit": 10})
    trace.step("answer", "qa", "No model available: listed the matching findings.", tool="list", detail={"args": args, "rows": len(rows)})
    if not rows:
        return {"answer": "No findings match that question in this run.", "finding_ids": [], "used_model": False, "steps": trace.steps}
    lines = [f"#{r['finding_id']} ({r['check_id']}, {r['status']}{', ' + r['severity'] if r['severity'] else ''}): {r['reason']}" for r in rows]
    return {"answer": f"The {len(rows)} most relevant findings:\n" + "\n".join(lines), "finding_ids": ids, "used_model": False, "steps": trace.steps}


def ask(run_id: UUID, question: str) -> dict:
    """Answer one question about a run. Returns {answer, finding_ids, used_model, steps}."""
    trace = Trace(None)
    question = question.strip()[:500]
    if not question:
        raise ValueError("Ask a question about this audit.")
    if not llm.available():
        return _fallback(run_id, question, trace)
    seen_ids: set[int] = set()
    log: list[str] = []
    system = ("You answer an auditor's question about one completed audit run, using only the query tools. State only what the tool results show; "
              "never guess a number. When you state a fact about particular findings, list their ids in finding_ids. If the tools cannot answer, say so.")
    for step in range(1, MAX_STEPS + 1):
        prompt = f"Question: {question}\n\n{_MENU}\n\nResults so far:\n" + ("\n".join(log) if log else "(none)") + \
                 ("\n\nThis is your last step: answer now." if step == MAX_STEPS else "")
        try:
            move = llm.reason_json(prompt, system, max_tokens=1200)
        except llm.LLMError as exc:
            trace.step("answer", "qa", f"The model could not be used ({exc}); answering without it.", status="info")
            return _fallback(run_id, question, trace)
        if not isinstance(move, dict):
            break
        if move.get("action") == "answer" and move.get("answer"):
            cited = [int(i) for i in move.get("finding_ids") or [] if str(i).isdigit()]
            bad = [i for i in cited if i not in seen_ids]
            if bad:  # a finding the tools never returned: refuse rather than pass it on
                trace.step("answer", "qa", f"Rejected an answer citing finding(s) {bad} that no query returned.", status="failed")
                log.append(f"Your answer cited ids {bad} that no tool returned. Use only ids from the results.")
                continue
            trace.step("answer", "qa", "Answered from the query results.", detail={"finding_ids": cited})
            return {"answer": str(move["answer"]).strip(), "finding_ids": cited, "used_model": True, "steps": trace.steps}
        name, args = str(move.get("tool", "")), move.get("args") or {}
        try:
            rows, ids = _run_tool(run_id, name, args)
        except Exception as exc:
            log.append(f"{name}: failed ({type(exc).__name__}). Try a different query.")
            trace.step("answer", "qa", f"{name} failed: {type(exc).__name__}", tool=name, status="failed")
            continue
        seen_ids.update(ids)
        trace.step("answer", "qa", f"Ran {name} {args or ''}: {len(rows)} row(s).", tool=name, detail={"args": args, "rows": len(rows)})
        log.append(f"{name} {args}: {rows}")
    return {"answer": "I could not reach an answer I can support from this run's findings within the step limit. Try a narrower question, "
                      "such as one check or one status.", "finding_ids": [], "used_model": True, "steps": trace.steps}
