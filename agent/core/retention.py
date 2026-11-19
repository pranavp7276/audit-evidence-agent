"""The retention window: the platform keeps six months of activity (docs/decisions.md D-030).

Calls, recordings, transcripts, messages and notices older than the horizon are purged (python -m agent retention). Standing records that a result
in the window can depend on are kept: consent events, certificates, collector status, registered caller IDs, templates and D12 rules. An audit
asks about a period; if the period starts before the horizon, the records for the earlier part are not held, and the audit says so.
"""
from __future__ import annotations

import calendar
from datetime import date

RETENTION_MONTHS = 6


def horizon(today: date | None = None) -> date:
    """The first day whose activity is kept: today less six months (the same day of the month, or the last day of a shorter month)."""
    today = today or date.today()
    y, m = divmod(today.year * 12 + today.month - 1 - RETENTION_MONTHS, 12)
    return date(y, m + 1, min(today.day, calendar.monthrange(y, m + 1)[1]))


def period_note(period: dict | None, today: date | None = None) -> str | None:
    """Plain words for an audit period that reaches back past the retention window, or None when it does not."""
    if not period:
        return None
    h = horizon(today)
    start = date.fromisoformat(period["start"])
    if start >= h:
        return None
    return (f"The platform keeps {RETENTION_MONTHS} months of activity, so calls, messages and notices before {h:%d %B %Y} are no longer held. "
            f"The part of this period from {start:%d %B %Y} to {h:%d %B %Y} cannot be evidenced from the records here; "
            "anything that depends on them is cannot determine, never compliant.")
