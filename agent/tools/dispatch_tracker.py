"""Dispatch tracker: notices (trigger, dispatch, service) and the holiday calendar."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@tool("dispatch_tracker", sources=("Notice dispatch history",))
def get_notices(account_id: str) -> list[dict]:
    """Notices for an account. Each row: notice_id, notice_type, borrower_state, trigger_date, dispatch_date (None if never
    dispatched), served_date (None if never served), plus citation fields. Dates have no zone, so no timestamp."""
    rows = query("SELECT * FROM staging.notices WHERE account_id = %s ORDER BY trigger_date, notice_id", (account_id,))
    return [with_citation(r, "notice_dispatch", "compliance.notice", "notice_id") for r in rows]


@lru_cache(maxsize=1)
def get_holidays() -> tuple[dict, ...]:
    """The holiday calendar. Each row: holiday_date, holiday_name, scope, state, plus citation fields."""
    rows = query("SELECT * FROM staging.holidays ORDER BY holiday_date, scope, state")
    return tuple(with_citation(r, "holiday_calendar", "compliance.holiday_calendar", "holiday_id") for r in rows)


def national_holidays(start: date, end: date) -> list[dict]:
    """National holidays in (start, end]."""
    return [h for h in get_holidays() if h["scope"] == "national" and start < h["holiday_date"] <= end]


def add_business_days(start: date, n: int) -> tuple[date, list[dict]]:
    """The date n business days after start (Mon-Fri, national holidays excluded), and the holidays skipped on the way."""
    hol = {h["holiday_date"]: h for h in get_holidays() if h["scope"] == "national"}
    d, skipped = start, []
    while n > 0:
        d += timedelta(days=1)
        if d in hol:
            skipped.append(hol[d])
        elif d.weekday() < 5:
            n -= 1
    return d, skipped


def business_days_between(start: date, end: date) -> int:
    """Business days in (start, end], same calendar."""
    hol = {h["holiday_date"] for h in get_holidays() if h["scope"] == "national"}
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in hol:
            n += 1
    return n
