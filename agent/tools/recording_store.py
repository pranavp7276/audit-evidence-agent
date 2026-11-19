"""Recording and transcript store: was each call recorded, and what was said."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _recordings(account_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.d10_recordings WHERE account_id = %s ORDER BY recorded_ts_utc", (account_id,))
    return tuple(with_citation(r, "D10", "raw.d10", "recording_id", "recorded_ts") for r in rows)


def get_recordings(account_id: str, start: datetime | None = None,
                   end: datetime | None = None) -> list[dict]:
    """Recording metadata for an account. A call with no row here is a missing recording."""
    return [r for r in _recordings(account_id)
            if (start is None or r["recorded_ts_utc"] >= start) and (end is None or r["recorded_ts_utc"] < end)]


def get_transcript(call_id: str) -> dict | None:
    """Transcript for one call. There is no transcript store in this dataset, so this is always None
    (cannot_determine from a transcript, never a pass); verification is tested from D11 instead."""
    return None
