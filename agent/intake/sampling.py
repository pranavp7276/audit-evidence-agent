"""Who is audited: the period, how many accounts were reached out to, the repeatable random sample, and matching the account references a request lists."""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time

from agent.core.clock import RULE_TZ
from agent.tools.warehouse_sql import run_sql

MAX_SAMPLE = 2000


def period_bounds(period: dict) -> tuple[datetime, datetime]:
    """[start, end) of a period in UTC; its dates are India calendar days (docs/decisions.md D-014)."""
    def bound(iso: str) -> datetime:
        return datetime.combine(date.fromisoformat(iso), time.min, tzinfo=RULE_TZ).astimezone(UTC)
    return bound(period["start"]), bound(period["end"])


def _reached_out(period: dict | None) -> tuple[str, dict]:
    """SQL for the accounts reached out to: an outbound call attempt (counted once) or a message sent in the period."""
    if not period:
        return ("SELECT account_id FROM staging.call_sessions WHERE direction = 'OUTBOUND' AND NOT is_mirror_duplicate "
                "UNION SELECT account_id FROM staging.messages WHERE status IN ('SENT', 'DELIVERED', 'READ')", {})
    start, end = period_bounds(period)
    return ("SELECT account_id FROM staging.call_sessions WHERE direction = 'OUTBOUND' AND NOT is_mirror_duplicate "
            "AND started_ts_utc >= %(start)s AND started_ts_utc < %(end)s "
            "UNION SELECT account_id FROM staging.messages WHERE status IN ('SENT', 'DELIVERED', 'READ') AND sent_ts_utc >= %(start)s AND sent_ts_utc < %(end)s",
            {"start": start, "end": end})


def contacted_accounts(period: dict | None) -> int:
    """How many accounts were reached out to in the period (all accounts when there is no period)."""
    sql, params = _reached_out(period)
    return run_sql(f"SELECT count(*) AS n FROM ({sql}) t", params)["rows"][0]["n"]


def sample_accounts(period: dict | None, size: int | None, seed: str) -> list[str]:
    """A random sample of the accounts reached out to in the period. Ordered by a hash of the account id and the
    request reference, so re-running the same request draws the same sample."""
    sql, params = _reached_out(period)
    limit = min(size or MAX_SAMPLE, MAX_SAMPLE)
    out = run_sql(f"SELECT account_id FROM ({sql}) t ORDER BY md5(account_id || %(seed)s), account_id LIMIT %(lim)s", {**params, "seed": seed, "lim": limit}, max_rows=limit)
    return [r["account_id"] for r in out["rows"]]


def resolve_references(refs: list[str]) -> list[dict]:
    """Match each account reference the auditor wrote to a CN account. A reference is a loan account number or a CN
    account id. One match is 'matched'; none is 'unmatched'; several (the same number under two institutions) is
    'ambiguous'. Nothing is dropped: every reference comes back with its status."""
    if not refs:
        return []
    rows = run_sql("SELECT account_id, account_number, institution_code FROM staging.accounts "
                   "WHERE upper(account_number) = ANY(%(numbers)s) OR account_id = ANY(%(ids)s)", {"numbers": [r.upper() for r in refs], "ids": list(refs)}, max_rows=20000)["rows"]
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
