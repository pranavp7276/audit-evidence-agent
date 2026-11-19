"""Contact log (D4): every attempt and contact, by account, collector and channel."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _all_contacts(account_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.d4_contacts WHERE account_id = %s ORDER BY contact_ts_utc, contact_id", (account_id,))
    return tuple(with_citation(r, "D4", "raw.d4_contact_log", "contact_id", "contact_ts") for r in rows)


def get_contacts(account_id: str, start: datetime | None = None, end: datetime | None = None,
                 channel: str | None = None) -> list[dict]:
    """All contact events for an account in [start, end), ordered by contact time (UTC).

    Each row: contact_id, account_id, collector_id, channel, contact_ts_utc, contact_ts_src,
    contact_ts_src_tz, outcome, dues_disclosed, plus citation fields (source_system, source_table,
    record_key, record_ts_utc, record_ts_original).
    """
    return [r for r in _all_contacts(account_id)
            if (start is None or r["contact_ts_utc"] >= start) and (end is None or r["contact_ts_utc"] < end)
            and (channel is None or r["channel"] == channel)]
