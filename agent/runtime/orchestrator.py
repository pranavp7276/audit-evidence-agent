"""The orchestrator: runs one audit as plan -> retrieve and evaluate -> investigate, recording every step in the trace.

It owns the order of work and nothing else. The planner decides what will be done, the checks (with their tools) decide each result,
and the investigator widens the search where evidence is missing. A run is bounded: one pass per check, at most MAX_RETRIES retries
per failed account, one mirror lookup per provisional call. Whatever is still unresolved is reported as such.

It never writes. The audit service (agent/services/audit.py) saves the findings and the trace.
"""
from __future__ import annotations

import time
from collections.abc import Callable

from agent.checks import REGISTRY
from agent.core.context import current_check, current_trace
from agent.core.contracts import CheckSpec, Finding, Status
from agent.core.trace import Trace
from agent.runtime.investigator import Investigator
from agent.runtime.planner import build_plan


def _counts(findings: list[Finding]) -> dict[str, int]:
    return {s.value: sum(f.status is s for f in findings) for s in (Status.EVIDENCED, Status.GAP, Status.CANNOT_DETERMINE)}


def run_agent(trace: Trace, checks: list[CheckSpec], scale: list[str], sample: list[str], origin: str, period: dict | None,
              unresolved_refs: int, log: Callable[[str], None] = print) -> dict[str, list[Finding]]:
    """Plan, test and investigate. Returns the findings by check id; the caller saves them and the trace."""
    trace_token = current_trace.set(trace)
    results: dict[str, list[Finding]] = {}
    try:
        build_plan(checks, len(sample), period, origin, unresolved_refs, trace)
        trace.flush_tool_stats(None)  # the warehouse queries that drew the sample, made before the plan was written
        runnable = []
        for spec in checks:
            cls = REGISTRY.get(spec.check_type)
            if cls is None:
                log(f"  {spec.check_id}: no test for check type '{spec.check_type.value}'; reported as not tested")
                continue
            runnable.append(spec)
            trace.step("evaluate", "evaluator", f"{spec.check_id}: retrieving the evidence and testing {len(sample):,} account(s)...", check_id=spec.check_id, status="info")
            t0 = time.perf_counter()
            check_token = current_check.set(spec.check_id)
            try:
                findings = cls(spec, scale).run(sample)
            finally:
                current_check.reset(check_token)
            trace.flush_tool_stats(spec.check_id)
            results[spec.check_id] = findings
            n = _counts(findings)
            failed = sum(f.reason.startswith("Check failed to run") for f in findings)
            trace.step("evaluate", "evaluator", f"{spec.check_id}: tested {len(sample):,} account(s): {n['evidenced']} evidenced, {n['gap']} gap(s), "
                       f"{n['cannot_determine']} cannot determine" + (f" ({failed} failed to run)" if failed else "") + ". Results come from the check's rules, not a model.",
                       check_id=spec.check_id, status="failed" if failed else "ok", detail=n, ms=(time.perf_counter() - t0) * 1000)
            log(f"  {spec.check_id} {spec.check_type.value}: {len(sample)} accounts, {n}")
        Investigator(trace).review(runnable, scale, results)
        for spec in runnable:
            trace.flush_tool_stats(spec.check_id)
        return results
    finally:
        current_trace.reset(trace_token)
