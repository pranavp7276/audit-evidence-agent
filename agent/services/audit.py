"""The audit use case, shared by the command line and the web app: read, sample, apply guardrails, run the agent, save.

This is the only place that ties intake, the agent runtime and persistence together. Each step is its own function, so a run reads as a list.
"""
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from agent.core.contracts import CheckSpec, Request
from agent.core.trace import Trace
from agent.intake.request_parser import parse_checks, parse_sample
from agent.intake.sampling import resolve_references, sample_accounts
from agent.knowledge.guardrails import published_for
from agent.runtime.orchestrator import run_agent
from agent.services import store
from agent.tools import clear_caches


def choose_sample(run_id: UUID, request: Request, accounts: list[str] | None, period: dict | None, size: int | None) -> tuple[list[str], str, int]:
    """The sample, in order: the references supplied, the references the request lists, or a random sample of the accounts reached
    out to in the period. References are matched to CN accounts first; unmatched and ambiguous ones are recorded and left untested.
    Returns (account ids, where they came from, how many references were not matched)."""
    if accounts:
        resolved = resolve_references(accounts)
        store.save_sample_references(run_id, resolved)
        sample = [r["account_id"] for r in resolved if r["status"] == "matched"]
        if not sample:
            raise ValueError("None of the account references in the request matched a loan account, so nothing can be tested.")
        origin = (f"{len(accounts)} account references: {len(sample)} matched, {sum(r['status'] == 'unmatched' for r in resolved)} unmatched, "
                  f"{sum(r['status'] == 'ambiguous' for r in resolved)} ambiguous")
        return sample, origin, sum(r["status"] != "matched" for r in resolved)
    if not (period or size):
        raise ValueError("No sampled accounts: the request lists none, gives no period and no sample size. "
                         "Supply an account list, a period, or a sample size.")
    sample = sample_accounts(period, size, request.request_id)
    if not sample:
        raise ValueError("No accounts were reached out to in that period, so there is nothing to sample.")
    store.save_sample_references(run_id, [dict(ref=a, status="matched", account_id=a, candidates=[a], note="Drawn by the platform") for a in sample])
    return sample, f"random sample of {len(sample)} accounts" + (f" reached out to in {period['label']}" if period else ""), 0


def apply_scope(checks: list[CheckSpec], sample: list[str], origin: str, period: dict | None) -> None:
    """Give every check its sample, the period, and the guardrail version it applies with that guardrail's default severity and review weight."""
    for c in checks:
        c.sample = {"source": origin, "accounts": len(sample), **({"period": period} if period else {})}
        if period:
            c.test = {**c.test, "period": period}
        g = published_for(c.check_type.value) if c.check_type.value != "other" else None
        if g:
            c.test = {**c.test, "guardrail": {"id": g["guardrail_id"], "version": g["version"], "title": g["title"]},
                      "default_severity": g["default_severity"], "priority_weight": g["priority_weight"]}


def process(run_id: UUID, request: Request, accounts: list[str] | None = None, random_n: int | None = None,
            log: Callable[[str], None] = print, checks: list[CheckSpec] | None = None,
            scale: list[str] | None = None, period: dict | None = None, size: int | None = None) -> None:
    """Run every check for an already-started run. Marks the run completed or failed and re-raises so a caller can show the error.
    The period (from the request unless given) limits which calls and messages every check tests."""
    trace = Trace(run_id)
    try:
        clear_caches()
        if checks is None:  # no reviewed interpretation supplied: let the parser read the request
            checks, scale = parse_checks(request)
        if not checks:  # never "complete" a run that tested nothing
            raise ValueError("No checks could be made from this request. Say what to test (for example 'run a compliance "
                             "audit of all guardrails for accounts contacted last month') or number the questions Q1, Q2, ...")
        scale = scale or []
        request.severity_scale = scale
        store.set_severity_scale(run_id, scale)
        stated = parse_sample(request.text)
        period = period or stated["period"]
        sample, origin, unmatched = choose_sample(run_id, request, accounts or stated["accounts"], period, size or random_n or stated["size"])
        apply_scope(checks, sample, origin, period)
        store.save_checks(run_id, checks, {c.check_id: sample for c in checks})
        results = run_agent(trace, checks, scale, sample, origin, period, unmatched, log)
        for findings in results.values():
            store.save_findings(run_id, findings)
        total = {s: sum(f.status.value == s for fs in results.values() for f in fs) for s in ("evidenced", "gap", "cannot_determine")}
        trace.step("report", "reporter", f"Saved {sum(total.values()):,} finding(s): {total['evidenced']} evidenced, {total['gap']} gap(s), "
                   f"{total['cannot_determine']} cannot determine. Every evidenced result and gap has its citations; the run took {trace.elapsed_ms() / 1000:.1f}s.",
                   detail=total)
        store.finish_run(run_id, "completed")
    except Exception as exc:
        trace.step("report", "reporter", f"The run stopped: {type(exc).__name__}: {exc}", status="failed")
        store.finish_run(run_id, "failed", notes=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        try:
            trace.save()
        except Exception as exc:  # the trace explains a run; losing it must not hide the run's own outcome
            log(f"  (could not save the agent trace: {exc})")
