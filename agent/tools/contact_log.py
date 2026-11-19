"""Contact log (D4): every attempt and contact, by account, collector and channel."""
from __future__ import annotations

from datetime import datetime


def get_contacts(account_id: str, start: datetime | None = None, end: datetime | None = None,
                 channel: str | None = None) -> list[dict]:
    """All contact events for an account in [start, end), ordered by contact time (UTC).

    Each row: contact_id, account_id, collector_id, channel, contact_ts_utc, contact_ts_src,
    contact_ts_src_tz, plus citation fields (source_system, source_table, record_key).
    TODO(owner): implement over staging.d4_* once it exists.
    """
    raise NotImplementedError
