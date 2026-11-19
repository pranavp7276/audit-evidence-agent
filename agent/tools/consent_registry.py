"""Consent registry (D5): consent records per account and channel."""
from __future__ import annotations

from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _consents(account_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.d5_consents WHERE account_id = %s ORDER BY consent_ts_utc", (account_id,))
    return tuple(with_citation(r, "D5", "raw.d5", "consent_id", "consent_ts") for r in rows)


def get_consents(account_id: str, channel: str | None = None) -> list[dict]:
    """Consent records for an account (optionally one channel), ordered by consent time (UTC).

    Each row: consent_id, channel, consent_ts_utc, consent_ts_src, status, plus citation fields."""
    return [r for r in _consents(account_id) if channel is None or r["channel"] == channel]
