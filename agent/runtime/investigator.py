"""The investigator: after the evaluator's first pass it asks, for each result, "does the evidence I found actually prove this?"

A first-pass result built on missing evidence is provisional. The investigator:

1. Retries an account whose check failed to run (a failed retrieval is never a pass, and it may be transient).
2. Looks for the evidence somewhere else before concluding it is missing: a recording the primary dialer cannot produce may be held by the
   other dialer that mirrored the call. It points the tools at the mirrored sessions and re-evaluates only the affected accounts. A
   "no recording" gap or an unreadable recording is therefore only confirmed once the mirrored copy has been tried too.
3. Leaves whatever is still unresolved as it is, for a person: cannot determine stays cannot determine, a confirmed gap stays a gap.

It never decides pass or fail: re-evaluation runs the same deterministic check. It only widens where the evidence is looked for, and
every step is written to the trace.
"""
from __future__ import annotations

import time
from collections import defaultdict

from agent.checks import REGISTRY
from agent.core.context import alt_evidence, current_check
from agent.core.contracts import CheckSpec, CheckType, Finding, Status
from agent.core.trace import Trace
from agent.tools.session_mirrors import get_mirror_keys

MAX_RETRIES = 2
# check types whose result can depend on evidence held in another system, and which statuses are provisional for each
_MIRRORABLE = {CheckType.RECORDING_COMPLETENESS: {Status.GAP, Status.CANNOT_DETERMINE}, CheckType.VERIFICATION_BEFORE_DISCLOSURE: {Status.CANNOT_DETERMINE}}


class Investigator:
    def __init__(self, trace: Trace):
        self.trace = trace

    def review(self, specs: list[CheckSpec], scale: list[str], results: dict[str, list[Finding]]) -> dict[str, int]:
        t0 = time.perf_counter()
        stats = {"retried": 0, "retry_resolved": 0, "mirror_examined": 0, "mirror_resolved": 0, "no_alternative": 0}
        by_id = {s.check_id: s for s in specs}
        for cid, findings in list(results.items()):
            spec = by_id[cid]
            cls = REGISTRY.get(spec.check_type)
            if cls is None or not findings:
                continue
            self._retry_failed(spec, cls, scale, results, stats)
            if spec.check_type in _MIRRORABLE:
                self._look_in_mirrors(spec, cls, scale, results, stats)
        unresolved = sum(1 for fs in results.values() for f in fs if f.status is Status.CANNOT_DETERMINE)
        self.trace.step("investigate", "investigator",
                        f"Finished reviewing. {stats['retry_resolved']} of {stats['retried']} failed account(s) recovered on retry; "
                        f"{stats['mirror_resolved']} of {stats['mirror_examined']} call(s) with a mirrored session now have their evidence; "
                        f"{stats['no_alternative']} had no other system to ask. {unresolved} finding(s) remain cannot-determine and are queued for follow-up.",
                        status="info", detail={**stats, "queued_for_follow_up": unresolved}, ms=(time.perf_counter() - t0) * 1000)
        return stats

    # ---- 1. a check that crashed for an account is retried, never treated as a pass
    def _retry_failed(self, spec, cls, scale, results, stats) -> None:
        failed = sorted({f.account_id for f in results[spec.check_id] if f.status is Status.CANNOT_DETERMINE and f.reason.startswith("Check failed to run")})
        for account in failed:
            stats["retried"] += 1
            outcome = None
            for attempt in range(1, MAX_RETRIES + 1):
                time.sleep(0.4 * attempt)
                new = self._run(cls, spec, scale, account)
                if not any(f.reason.startswith("Check failed to run") for f in new):
                    outcome = new
                    break
                self.trace.step("investigate", "investigator", f"Retry {attempt} for account {account} failed again.", check_id=spec.check_id, account_id=account, status="retry")
            if outcome is not None:
                self._replace(results, spec.check_id, account, outcome)
                stats["retry_resolved"] += 1
                self.trace.step("investigate", "investigator", f"Account {account} recovered on retry.", check_id=spec.check_id, account_id=account, status="resolved")
            else:
                self.trace.step("investigate", "investigator", f"Account {account} still fails after {MAX_RETRIES} retries; left cannot-determine for follow-up.",
                                check_id=spec.check_id, account_id=account, status="unresolved")

    # ---- 2. evidence missing here may exist under the mirrored session
    def _look_in_mirrors(self, spec, cls, scale, results, stats) -> None:
        provisional = _MIRRORABLE[spec.check_type]
        sessions: dict[str, set[str]] = defaultdict(set)  # account -> its provisional sessions
        for f in results[spec.check_id]:
            if f.status in provisional and f.subject_ref and ":" in f.subject_ref:
                sessions[f.account_id].add(f.subject_ref)
        if not sessions:
            return
        t0 = time.perf_counter()
        all_keys = sorted({k for ks in sessions.values() for k in ks})
        token = current_check.set(spec.check_id)
        try:
            mirrors = get_mirror_keys(all_keys)
        finally:
            current_check.reset(token)
        with_mirror = {a: {k: mirrors[k] for k in ks if k in mirrors} for a, ks in sessions.items()}
        with_mirror = {a: m for a, m in with_mirror.items() if m}
        no_alt = len(all_keys) - len([k for m in with_mirror.values() for k in m])
        stats["no_alternative"] += no_alt
        self.trace.step("investigate", "investigator",
                        f"{spec.check_id}: {len(all_keys)} call(s) have a result that rests on missing or unreadable evidence; "
                        f"{len(all_keys) - no_alt} were also logged by the other dialer (asked for their recording and transcript), {no_alt} have no other system to ask.",
                        tool="session_mirrors", check_id=spec.check_id, detail={"provisional_calls": len(all_keys), "with_mirror": len(all_keys) - no_alt, "without": no_alt},
                        ms=(time.perf_counter() - t0) * 1000)
        for account, alt in sorted(with_mirror.items()):
            stats["mirror_examined"] += len(alt)
            before = {f.subject_ref: f.status.value for f in results[spec.check_id] if f.account_id == account and f.subject_ref in alt}
            token = alt_evidence.set(alt)
            try:
                new = self._run(cls, spec, scale, account)
            finally:
                alt_evidence.reset(token)
            after = {f.subject_ref: f.status.value for f in new if f.subject_ref in alt}
            moved = {k: (before.get(k), after.get(k)) for k in alt if before.get(k) != after.get(k)}
            if moved:
                self._replace(results, spec.check_id, account, new)
                stats["mirror_resolved"] += len(moved)
            self.trace.step("investigate", "investigator",
                            (f"Account {account}: found the evidence under a mirrored session for {len(moved)} call(s); re-evaluated. "
                             + "; ".join(f"{k}: {a} -> {b or 'now part of the evidenced result'}" for k, (a, b) in moved.items())) if moved else
                            f"Account {account}: looked under the mirrored session(s) for {len(alt)} call(s); nothing usable there, the result stands.",
                            check_id=spec.check_id, account_id=account, status="resolved" if moved else "unresolved", detail={"mirrors": alt, "before": before, "after": after})

    @staticmethod
    def _run(cls, spec, scale, account: str) -> list[Finding]:
        token = current_check.set(spec.check_id)
        try:
            return cls(spec, scale).run([account])
        finally:
            current_check.reset(token)

    @staticmethod
    def _replace(results: dict[str, list[Finding]], check_id: str, account: str, new: list[Finding]) -> None:
        results[check_id] = [f for f in results[check_id] if f.account_id != account] + new
