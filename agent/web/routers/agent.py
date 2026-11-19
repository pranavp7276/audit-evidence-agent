"""What the agent did on a run (its trace) and the "Ask the audit" question-answering agent."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from agent.core.toolkit import REGISTRY as TOOLS
from agent.runtime import qa
from agent.services.challenge import challenge_finding
from agent.web.common import _all, _completed, _run_or_404

router = APIRouter()

PHASES = [("plan", "Plan"), ("retrieve", "Retrieve"), ("evaluate", "Evaluate"), ("investigate", "Investigate"), ("challenge", "Second reading"), ("report", "Report")]


@router.get("/api/agent/tools")
def agent_tools() -> list[dict]:
    """The tools the agent can call: name, what it does and which source it reads."""
    return [{"name": t.name, "description": t.description, "sources": list(t.sources), "read_only": t.read_only} for t in TOOLS.values()]


@router.get("/api/runs/{run_id}/agent")
def run_agent_trace(run_id: UUID) -> dict:
    run = _run_or_404(run_id)
    steps = _all("SELECT seq, phase, agent, action, tool, check_id, account_id, status, detail, duration_ms FROM audit.agent_steps WHERE run_id = %s ORDER BY seq", (run_id,))
    by_phase = {p: sum(s["phase"] == p for s in steps) for p, _ in PHASES}
    inv = [s for s in steps if s["phase"] == "investigate"]
    return {"status": run["status"], "steps": steps, "phases": [{"key": p, "label": label, "steps": by_phase[p]} for p, label in PHASES],
            "summary": {"steps": len(steps), "investigations": len(inv), "resolved": sum(s["status"] == "resolved" for s in inv),
                        "unresolved": sum(s["status"] == "unresolved" for s in inv), "failed": sum(s["status"] == "failed" for s in steps),
                        "tool_calls": sum((s["detail"] or {}).get("calls", 0) for s in steps if s["phase"] == "retrieve"),
                        "ms": sum(s["duration_ms"] or 0 for s in steps if s["phase"] in ("evaluate", "investigate"))},
            "recorded": bool(steps)}


@router.post("/api/runs/{run_id}/ask")
async def ask_the_audit(run_id: UUID, request: Request) -> dict:
    _completed(run_id)
    body = await request.json()
    try:
        return qa.ask(run_id, str(body.get("question", "")))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/api/runs/{run_id}/findings/{finding_id}/challenge")
async def challenge(run_id: UUID, finding_id: int, request: Request) -> dict:
    """Ask a second model to read one gap against the records it cites. It changes nothing; the answer is shown beside the gap."""
    _completed(run_id)
    body = await request.json()
    who = str(body.get("requested_by", "")).strip()
    if not who:
        raise HTTPException(400, "Enter your name first.")
    try:
        return challenge_finding(run_id, finding_id, who)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
