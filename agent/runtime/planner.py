"""The planner: turns the auditor's confirmed checks into an explicit plan before anything is retrieved.

For each check it records which tools will be called and why, the guardrail version applied, the sample and period, and every
assumption or open point the auditor should know about (a period inferred from the wording, a default severity, references that were
not matched, a question the platform cannot test). The plan is saved to the trace, so a reviewer can see what the agent intended
and compare it with what it did. Which tools a check needs is declared by the check itself (its `tools` attribute), not hard-coded here.
"""
from __future__ import annotations

from agent.checks import REGISTRY
from agent.checks.catalog import CHECK_INFO
from agent.contracts import CheckSpec
from agent.runtime.tools import REGISTRY as TOOLS
from agent.runtime.trace import Trace


def build_plan(checks: list[CheckSpec], sample_size: int, period: dict | None, origin: str, unresolved_refs: int, trace: Trace) -> list[dict]:
    plan = []
    trace.step("plan", "planner", f"Plan for {len(checks)} check(s) over {sample_size:,} sampled account(s)"
               + (f" in {period['label']}" if period else " (no period stated: every contact on record)") + f". Sample: {origin}.",
               detail={"checks": len(checks), "accounts": sample_size, "period": period, "origin": origin})
    if unresolved_refs:
        trace.step("plan", "planner", f"{unresolved_refs} account reference(s) in the request are unmatched or ambiguous: they are kept visible and not tested.",
                   status="info", detail={"unresolved_references": unresolved_refs})
    for c in checks:
        cls = REGISTRY.get(c.check_type)
        title = CHECK_INFO[c.check_type.value]["title"]
        if cls is None:
            trace.step("plan", "planner", f"{c.check_id} ({title}): no test exists for this question, so it will be reported as unanswered, not dropped.",
                       check_id=c.check_id, status="info")
            plan.append({"check_id": c.check_id, "type": c.check_type.value, "tools": [], "note": "reported as unanswered"})
            continue
        tools = [t for t in cls.tools if t in TOOLS]
        notes = []
        if not c.test.get("severity"):
            notes.append(f"no severity in the request: the guardrail default ({c.test.get('default_severity', 'most severe on the scale')}) applies")
        g = c.test.get("guardrail")
        trace.step("plan", "planner", f"{c.check_id} ({title}): call " + ", ".join(tools) + (f"; guardrail v{g['version']}" if g else "") + ("; " + "; ".join(notes) if notes else ""),
                   check_id=c.check_id, detail={"tools": tools, "guardrail": g, "notes": notes, "severity": c.test.get("severity")})
        plan.append({"check_id": c.check_id, "type": c.check_type.value, "tools": tools, "guardrail": g, "notes": notes})
    return plan
