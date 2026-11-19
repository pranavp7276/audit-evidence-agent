"""The whole run, shared by the command line and the web app: parse, sample, test, save."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from uuid import UUID

from agent import store
from agent.checks import REGISTRY
from agent.checks.base import RULE_TZ
from agent.contracts import CheckSpec, Request
from agent.db import read_rows
from agent.parser.request_parser import parse_checks, parse_sample
from agent.tools import clear_caches

MAX_SAMPLE = 2000


def period_bounds(period: dict) -> tuple[datetime, datetime]:
    """[start, end) of a period in UTC; its dates are India calendar days (docs/decisions.md D-014)."""
    def bound(iso: str) -> datetime:
        return datetime.combine(date.fromisoformat(iso), time.min, tzinfo=RULE_TZ).astimezone(UTC)
    return bound(period["start"]), bound(period["end"])


def _reached_out(period: dict | None) -> tuple[str, list]:
    """SQL for the accounts reached out to: an outbound call attempt (counted once) or a message sent in the period."""
    if not period:
        return ("SELECT account_id FROM staging.call_sessions WHERE direction = 'OUTBOUND' AND NOT is_mirror_duplicate "
                "UNION SELECT account_id FROM staging.messages WHERE status IN ('SENT', 'DELIVERED', 'READ')", [])
    start, end = period_bounds(period)
    return ("SELECT account_id FROM staging.call_sessions WHERE direction = 'OUTBOUND' AND NOT is_mirror_duplicate "
            "AND started_ts_utc >= %s AND started_ts_utc < %s "
            "UNION SELECT account_id FROM staging.messages WHERE status IN ('SENT', 'DELIVERED', 'READ') AND sent_ts_utc >= %s AND sent_ts_utc < %s",
            [start, end, start, end])


def contacted_accounts(period: dict | None) -> int:
    """How many accounts were reached out to in the period (all accounts when there is no period)."""
    sql, params = _reached_out(period)
    return read_rows(f"SELECT count(*) AS n FROM ({sql}) t", tuple(params))[0]["n"]


def sample_accounts(period: dict | None, size: int | None, seed: str) -> list[str]:
    """A random sample of the accounts reached out to in the period. Ordered by a hash of the account id and the
    request reference, so re-running the same request draws the same sample."""
    sql, params = _reached_out(period)
    rows = read_rows(f"SELECT account_id FROM ({sql}) t ORDER BY md5(account_id || %s), account_id LIMIT %s",
                     (*params, seed, min(size or MAX_SAMPLE, MAX_SAMPLE)))
    return [r["account_id"] for r in rows]


def resolve_references(refs: list[str]) -> list[dict]:
    """Match each account reference the auditor wrote to a CN account. A reference is a loan account number or a CN
    account id. One match is 'matched'; none is 'unmatched'; several (the same number under two institutions) is
    'ambiguous'. Nothing is dropped: every reference comes back with its status."""
    if not refs:
        return []
    rows = read_rows("SELECT account_id, account_number, institution_code FROM staging.accounts "
                     "WHERE upper(account_number) = ANY(%s) OR account_id = ANY(%s)", ([r.upper() for r in refs], list(refs)))
    index: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        index[r["account_number"].upper()][r["account_id"]] = r
        index[r["account_id"]][r["account_id"]] = r
    out = []
    for ref in refs:
        found = index.get(ref.upper()) or index.get(ref) or {}
        cands = sorted(found)
        if len(cands) == 1:
            out.append(dict(ref=ref, status="matched", account_id=cands[0], candidates=cands, note=None))
        elif not cands:
            out.append(dict(ref=ref, status="unmatched", account_id=None, candidates=[], note="No loan account has this number or id."))
        else:
            out.append(dict(ref=ref, status="ambiguous", account_id=None, candidates=cands,
                            note="Matches " + ", ".join(f"{found[c]['account_number']} ({found[c]['institution_code']}, id {c})" for c in cands)
                                 + ". Compliance must choose which loan is meant."))
    return out


def process(run_id: UUID, request: Request, accounts: list[str] | None = None, random_n: int | None = None,
            log: Callable[[str], None] = print, checks: list[CheckSpec] | None = None,
            scale: list[str] | None = None, period: dict | None = None, size: int | None = None) -> None:
    """Run every check for an already-started run. Marks the run completed or failed; never raises
    past the run record, but re-raises so a caller can show the error.

    The sample is, in order: the account references supplied, the references the request lists, or a random sample of
    the accounts reached out to in the period. References are matched to CN accounts first; unmatched and ambiguous
    ones are recorded and left untested. The period (from the request unless given) limits which calls and messages
    every check tests."""
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
        size = size or random_n or stated["size"]
        refs = accounts or stated["accounts"]
        if refs:
            resolved = resolve_references(refs)
            store.save_sample_references(run_id, resolved)
            sample = [r["account_id"] for r in resolved if r["status"] == "matched"]
            origin = f"{len(refs)} account references: {len(sample)} matched, {sum(r['status'] == 'unmatched' for r in resolved)} unmatched, " \
                     f"{sum(r['status'] == 'ambiguous' for r in resolved)} ambiguous"
            if not sample:
                raise ValueError("None of the account references in the request matched a loan account, so nothing can be tested.")
        else:
            if not (period or size):
                raise ValueError("No sampled accounts: the request lists none, gives no period and no sample size. "
                                 "Supply an account list, a period, or a sample size.")
            sample = sample_accounts(period, size, request.request_id)
            origin = f"random sample of {len(sample)} accounts" + (f" reached out to in {period['label']}" if period else "")
            store.save_sample_references(run_id, [dict(ref=a, status="matched", account_id=a, candidates=[a], note="Drawn by the platform") for a in sample])
        if not sample:
            raise ValueError("No accounts were reached out to in that period, so there is nothing to sample.")
        for c in checks:
            c.sample = {"source": origin, "accounts": len(sample), **({"period": period} if period else {})}
            if period:
                c.test = {**c.test, "period": period}
        store.save_checks(run_id, checks, {c.check_id: sample for c in checks})
        for spec in checks:
            check_cls = REGISTRY.get(spec.check_type)
            if check_cls is None:
                log(f"  {spec.check_id}: no test for check type '{spec.check_type.value}'; reported as not tested")
                continue
            findings = check_cls(spec, scale).run(sample)
            store.save_findings(run_id, findings)
            n = {s: sum(f.status.value == s for f in findings) for s in ("evidenced", "gap", "cannot_determine")}
            log(f"  {spec.check_id} {spec.check_type.value}: {len(sample)} accounts, {n}")
        store.finish_run(run_id, "completed")
    except Exception as exc:
        store.finish_run(run_id, "failed", notes=f"{type(exc).__name__}: {exc}")
        raise
