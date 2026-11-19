"""Apply the retention window: remove activity older than the horizon, keep the standing records (agent/core/retention.py)."""
from __future__ import annotations

from datetime import UTC, date, datetime, time

from agent.core.clock import RULE_TZ
from agent.core.db import connect
from agent.core.retention import horizon

# a session is old when its first status row started before the cutoff (the dialer's own zone is converted first)
_OLD_SESSIONS = """CREATE TEMP TABLE old_sessions ON COMMIT DROP AS
    SELECT l.dialer_code, l.call_session_id FROM cn_core.tele_process_instance_call_logs l JOIN compliance.dialer_config dc ON dc.dialer_code = l.dialer_code
    GROUP BY l.dialer_code, l.call_session_id, dc.timezone HAVING min(l.call_start_date_time AT TIME ZONE dc.timezone) < %(cutoff)s"""
_STEPS = [
    ("transcript turns", "DELETE FROM compliance.call_transcript_segment t USING old_sessions o WHERE t.dialer_code = o.dialer_code AND t.call_session_id = o.call_session_id"),
    ("recordings", "DELETE FROM compliance.call_recording t USING old_sessions o WHERE t.dialer_code = o.dialer_code AND t.call_session_id = o.call_session_id"),
    ("mirrored-call links", "DELETE FROM compliance.call_session_xref t USING old_sessions o WHERE (t.dialer_code = o.dialer_code AND t.call_session_id = o.call_session_id) "
                            "OR (t.mirror_dialer_code = o.dialer_code AND t.mirror_session_id = o.call_session_id)"),
    ("call-to-account links", "DELETE FROM cn_core.tele_process_instance_activity t USING old_sessions o WHERE t.dialer_code = o.dialer_code AND t.call_session_id = o.call_session_id"),
    ("call status rows", "DELETE FROM cn_core.tele_process_instance_call_logs t USING old_sessions o WHERE t.dialer_code = o.dialer_code AND t.call_session_id = o.call_session_id"),
    ("messages", "DELETE FROM cn_core.communication_dashboard_t WHERE message_datetime < %(cutoff_local)s"),
    ("notices", "DELETE FROM compliance.notice WHERE trigger_date < %(cutoff_date)s"),
    ("holidays", "DELETE FROM compliance.holiday_calendar WHERE holiday_date < %(cutoff_date)s"),
]


def purge(today: date | None = None, apply: bool = False) -> dict:
    """Remove activity older than the horizon. Without `apply` the same deletes run in a transaction that is rolled back, so the counts are exact and nothing changes."""
    h = horizon(today)
    params = {"cutoff_date": h, "cutoff": datetime.combine(h, time.min, tzinfo=RULE_TZ).astimezone(UTC), "cutoff_local": datetime.combine(h, time.min)}
    removed: dict[str, int] = {}
    with connect() as conn, conn.transaction(force_rollback=not apply):
        conn.execute(_OLD_SESSIONS, params)
        removed["calls"] = conn.execute("SELECT count(*) AS n FROM old_sessions").fetchone()["n"]
        for label, sql in _STEPS:
            removed[label] = conn.execute(sql, params).rowcount
    return {"horizon": h.isoformat(), "applied": apply, "removed": removed}
