"""Consent registry: when the borrower consented, for which channel, and any withdrawal."""
from __future__ import annotations


def get_consents(account_id: str, channel: str | None = None) -> list[dict]:
    """All consent and withdrawal events for an account, ordered by consent_ts_utc.

    TODO(owner): implement over the staging view for consent.
    """
    raise NotImplementedError
