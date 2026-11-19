"""The whole run, shared by the command line and the web app: parse, sample, test, save."""
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from agent import store
from agent.checks import REGISTRY
from agent.contracts import Request
from agent.db import read_rows
from agent.parser.request_parser import extract_sample_accounts, parse_checks
from agent.tools import clear_caches


def random_accounts(n: int) -> list[str]:
    rows = read_rows("SELECT account_id FROM (SELECT DISTINCT account_id FROM staging.d4_contacts) t "
                     "ORDER BY random() LIMIT %s", (n,))
    return [r["account_id"] for r in rows]


def process(run_id: UUID, request: Request, accounts: list[str] | None = None, random_n: int | None = None,
            log: Callable[[str], None] = print) -> None:
    """Run every check for an already-started run. Marks the run completed or failed; never raises
    past the run record, but re-raises so a caller can show the error."""
    try:
        clear_caches()
        checks, scale = parse_checks(request)
        request.severity_scale = scale
        store.set_severity_scale(run_id, scale)
        sample = accounts or extract_sample_accounts(request.text)
        origin = "supplied account list" if accounts else "request text"
        if not sample and random_n:
            sample, origin = random_accounts(random_n), f"random sample of {random_n}"
        if not sample:
            raise ValueError("No sampled accounts: the request lists none. Supply an account list or a random sample size.")
        for c in checks:
            c.sample = {"source": origin, "accounts": len(sample)}
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
