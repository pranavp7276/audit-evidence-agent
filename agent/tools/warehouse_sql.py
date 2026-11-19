"""Warehouse SQL: ad-hoc read-only queries for anything the specific tools don't cover."""
from __future__ import annotations

import re
from typing import Any

from agent.core.db import connect
from agent.core.toolkit import tool

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|vacuum)\b",
    re.IGNORECASE)
MAX_ROWS = 5000


@tool("warehouse_sql", sources=("Warehouse",))
def run_sql(query: str, params: dict[str, Any] | None = None, max_rows: int = MAX_ROWS) -> dict:
    """Run one read-only SELECT against staging.* and return rows.

    Returns {"query": str, "rows": [dict], "truncated": bool}. Keep the returned "query"
    with any finding built from it (Finding.evidence_query) so the result is reproducible.
    Defence in depth: keyword filter here, plus a read-only role and transaction in the DB.
    """
    stripped = query.strip().rstrip(";")
    if ";" in stripped:
        raise ValueError("One statement per call.")
    if not re.match(r"^\s*(select|with)\b", stripped, re.IGNORECASE) or _FORBIDDEN.search(stripped):
        raise ValueError("Only read-only SELECT / WITH queries are allowed.")
    with connect(read_only=True) as conn:
        cur = conn.execute(stripped, params or None)
        rows = cur.fetchmany(max_rows + 1)
    return {"query": stripped, "rows": rows[:max_rows], "truncated": len(rows) > max_rows}
