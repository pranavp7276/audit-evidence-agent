"""Collector status history: whether a collector was active on a given date (effective-dated, never overwritten)."""
from __future__ import annotations

from functools import lru_cache

from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _status(employee_code: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.collector_status WHERE employee_code = %s ORDER BY valid_from", (employee_code,))
    return tuple(with_citation(r, "collector_roster", "compliance.collector_status", "status_id") for r in rows)


@tool("collector_status", sources=("Collector status history",))
def get_collector_status(employee_code: str) -> list[dict]:
    """The status history of a collector by employee code. Each row: status_id, status (ACTIVE, INACTIVE or TERMINATED),
    valid_from and valid_to (both inclusive dates; valid_to is empty while it still holds), plus citation fields."""
    return list(_status(employee_code))
