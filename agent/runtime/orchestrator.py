"""The orchestrator: runs one audit as plan -> retrieve and evaluate -> investigate -> report, recording every step in the trace.

It owns the order of work and nothing else. The planner decides what will be done, the checks (with their tools) decide each result,
the investigator widens the search where evidence is missing, and the store saves. A run is bounded: one pass per check, at most
MAX_RETRIES retries per failed account, one mirror lookup per provisional call. Whatever is still unresolved is reported as such.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from uuid import UUID

from agent import store
from agent.checks import REGISTRY
from agent.contracts import CheckSpec, Finding, Status
from agent.runtime.context import current_check, current_trace
from agent.runtime.investigator import Investigator
from agent.runtime.planner import build_plan
from agent.runtime.trace import Trace


def _counts(findings: list[Finding]) -> dict[str, int]:
    return {s.value: sum(f.status is s for f in findings) for s in (Status.EVIDENCED, Status.GAP, Status.CANNOT_DETERMINE)}


def run_agent(run_id: UUID, checks: list[CheckSpec], scale: list[str], sample: list[str], origin: str, period: dict | None,
              unresolved_refs: int, log: Callable[[str], None] = print) -> dict[str, list[Finding]]:
    """Run the checks over the sample as an agent and save the findings and the trace. Returns the findings by check id."""
    trace = Trace(run_id)
    trace_token = current_trace.set(trace)
    results: dict[str, list[Finding]] = {}
    try:
        build_plan(checks, len(sample), period, origin, unresolved_refs, trace)
        runnable = []
        for spec in checks:
            cls = REGISTRY.get(spec.check_type)
            if cls is None:
                log(f"  {spec.check_id}: no test for check type '{spec.check_type.value}'; reported as not tested")
                continue
            runnable.append(spec)
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
        for spec in runnable:
            findings = results[spec.check_id]
            store.save_findings(run_id, findings)
        total = _counts([f for fs in results.values() for f in fs])
        trace.step("report", "reporter", f"Saved {sum(total.values()):,} finding(s): {total['evidenced']} evidenced, {total['gap']} gap(s), "
                   f"{total['cannot_determine']} cannot determine. Every evidenced result and gap has its citations; the run took {trace.elapsed_ms() / 1000:.1f}s.",
                   detail=total)
        return results
    except Exception as exc:
        trace.step("report", "reporter", f"The run stopped: {type(exc).__name__}: {exc}", status="failed")
        raise
    finally:
        current_trace.reset(trace_token)
        try:
            trace.save()
        except Exception as exc:  # the trace explains a run; losing it must not hide the run's own outcome
            log(f"  (could not save the agent trace: {exc})")
