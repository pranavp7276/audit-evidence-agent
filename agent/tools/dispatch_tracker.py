"""Dispatch tracker: notices sent, with dispatch and service dates, plus the holiday calendar."""
from __future__ import annotations

from datetime import date
from functools import lru_cache

from agent.tools._common import query, with_citation


def get_notices(account_id: str) -> list[dict]:
    """Notices for an account. Each row: notice_id, notice_type, borrower_state, trigger_date,
    dispatch_date, service_date (dates), plus citation fields (no timestamp: dates have no zone)."""
    rows = query("SELECT * FROM staging.notices WHERE account_id = %s ORDER BY trigger_date, notice_id", (account_id,))
    return [with_citation(r, "notice_dispatch", "raw.notice_dispatch", "notice_id") for r in rows]


@lru_cache(maxsize=1)
def get_holidays() -> tuple[dict, ...]:
    """The holiday calendar. Each row: holiday_date, holiday_name, scope, state, plus citation fields."""
    rows = query("SELECT * FROM staging.holidays ORDER BY holiday_date, scope, state")
    return tuple(with_citation(r, "holiday_calendar", "raw.holiday_calendar", "source_row") for r in rows)


def national_holidays(start: date, end: date) -> list[dict]:
    """National holidays in (start, end]."""
    return [h for h in get_holidays() if h["scope"] == "national" and start < h["holiday_date"] <= end]
