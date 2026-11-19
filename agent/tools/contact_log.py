"""Contact log: call sessions and messages from CN Core, qualified by dialer.

A call session is identified by (dialer, session id): SlashRTC and CognifAI ids are only unique within their own
dialer. A session can have several status rows (CONNECTED then DISPOSED); the platform keeps them as evidence
and counts the call once. A call mirrored in both dialers is counted under the canonical one only.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from agent.runtime.tools import tool
from agent.tools._common import query, with_citation

SENT_STATUSES = ("SENT", "DELIVERED", "READ")


@lru_cache(maxsize=4096)
def _calls(account_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.call_sessions WHERE account_id = %s ORDER BY started_ts_utc, session_key", (account_id,))
    return tuple(with_citation(r, "contact_log", "cn_core.tele_process_instance_call_logs", "session_key", "started_ts") for r in rows)


@tool("contact_log", sources=("CN Core call log",))
def get_calls(account_id: str, start: datetime | None = None, end: datetime | None = None, include_duplicates: bool = False,
              attempts_only: bool = False) -> list[dict]:
    """Call sessions for an account in [start, end), ordered by start time (UTC).

    Each row: session_key (dialer:session id), dialer_code, contact_no, direction, process_mode, employee_code,
    started_ts_utc / started_ts_src / started_ts_src_tz, statuses (every status row, kept as evidence), connected,
    counts_as_attempt (outbound and not a system failure), is_mirror_duplicate and mirror_of, plus citation fields.
    Mirrored duplicates are left out unless include_duplicates; attempts_only keeps only eligible attempts."""
    return [r for r in _calls(account_id)
            if (start is None or r["started_ts_utc"] >= start) and (end is None or r["started_ts_utc"] < end)
            and (include_duplicates or not r["is_mirror_duplicate"]) and (not attempts_only or r["counts_as_attempt"])]


@lru_cache(maxsize=4096)
def _messages(account_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.messages WHERE account_id = %s ORDER BY sent_ts_utc, message_id", (account_id,))
    return tuple(with_citation(r, "contact_log", "cn_core.communication_dashboard_t", "message_id", "sent_ts") for r in rows)


@tool("message_log", sources=("CN Core message log",))
def get_messages(account_id: str, start: datetime | None = None, end: datetime | None = None, channel: str | None = None) -> list[dict]:
    """Messages for an account in [start, end): message_id, channel, contact_no (recipient), sent_ts_utc, status,
    template_id and category (the purpose a recipient must have consented to), plus citation fields."""
    return [r for r in _messages(account_id)
            if (start is None or r["sent_ts_utc"] >= start) and (end is None or r["sent_ts_utc"] < end) and (channel is None or r["channel"] == channel)]
