"""The whole run, shared by the command line and the web app: parse, sample, test, save."""
from __future__ import annotations

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


def contacted_accounts(period: dict | None) -> int:
    """How many accounts had at least one contact in the period (all accounts when there is no period)."""
    if not period:
        return read_rows("SELECT count(DISTINCT account_id) AS n FROM staging.d4_contacts")[0]["n"]
    start, end = period_bounds(period)
    return read_rows("SELECT count(DISTINCT account_id) AS n FROM staging.d4_contacts "
                     "WHERE contact_ts_utc >= %s AND contact_ts_utc < %s", (start, end))[0]["n"]


def sample_accounts(period: dict | None, size: int | None, seed: str) -> list[str]:
    """A random sample of the accounts contacted in the period. Ordered by a hash of the account id and the
    request reference, so re-running the same request draws the same sample."""
    where, params = "", []
    if period:
        start, end = period_bounds(period)
        where, params = "WHERE contact_ts_utc >= %s AND contact_ts_utc < %s", [start, end]
    rows = read_rows(f"SELECT account_id FROM (SELECT DISTINCT account_id FROM staging.d4_contacts {where}) t "
                     "ORDER BY md5(account_id || %s), account_id LIMIT %s", (*params, seed, min(size or MAX_SAMPLE, MAX_SAMPLE)))
    return [r["account_id"] for r in rows]


def process(run_id: UUID, request: Request, accounts: list[str] | None = None, random_n: int | None = None,
            log: Callable[[str], None] = print, checks: list[CheckSpec] | None = None,
            scale: list[str] | None = None, period: dict | None = None, size: int | None = None) -> None:
    """Run every check for an already-started run. Marks the run completed or failed; never raises
    past the run record, but re-raises so a caller can show the error.

    The sample is, in order: the accounts supplied, the accounts the request lists, or a random sample of
    the accounts contacted in the period. The period (from the request unless given) limits which
    contacts every check tests."""
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
        sample = accounts or stated["accounts"]
        origin = "supplied account list" if accounts else "request text"
        if not sample:
            if not (period or size):
                raise ValueError("No sampled accounts: the request lists none, gives no period and no sample size. "
                                 "Supply an account list, a period, or a sample size.")
            sample = sample_accounts(period, size, request.request_id)
            origin = (f"random sample of {len(sample)} accounts" + (f" contacted in {period['label']}" if period else ""))
        if not sample:
            raise ValueError("No accounts were contacted in that period, so there is nothing to sample.")
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
