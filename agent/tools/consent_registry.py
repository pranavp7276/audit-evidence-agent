"""Consent registry: consent history per recipient number, channel and purpose."""
from __future__ import annotations

from functools import lru_cache

from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@lru_cache(maxsize=8192)
def _consents(contact_no: str, channel: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.consents WHERE contact_no = %s AND channel = %s ORDER BY effective_ts_utc, consent_id", (contact_no, channel))
    return tuple(with_citation(r, "consent_registry", "compliance.customer_consent", "consent_id", "effective_ts") for r in rows)


@tool("consent_registry", sources=("Consent registry",))
def get_consents(contact_no: str, channel: str) -> list[dict]:
    """The consent history for one recipient number on one channel, oldest first. Each row: consent_id, purpose,
    status (GRANTED or REVOKED), effective_ts_utc / effective_ts_src (UTC), capture_source, plus citation fields."""
    return list(_consents(contact_no, channel))
