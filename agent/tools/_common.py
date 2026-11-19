"""Shared helpers for the tools: every returned row carries the fields a Citation needs."""
from __future__ import annotations

from agent.core.db import read_rows


def query(sql: str, params: tuple | dict | None = None) -> list[dict]:
    return read_rows(sql, params)


def with_citation(row: dict, system: str, table: str, key: str, ts: str | None = None) -> dict:
    """Add source_system, source_table, record_key and the timestamps (UTC and as written in the source)."""
    out = dict(row)
    out.update(source_system=system, source_table=table, record_key=str(row[key]),
               record_ts_utc=row.get(f"{ts}_utc") if ts else None,
               record_ts_original=row.get(f"{ts}_src") if ts else None)
    return out
