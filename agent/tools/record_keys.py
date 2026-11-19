"""How a citation points at a source row, and a way to check that it still does.

KEY_EXPR gives, for each source table the checks cite, the SQL expression that equals the citation's record_key. The web app uses it to open a
cited record; verify_records uses it to read every cited record back from the warehouse.
"""
from __future__ import annotations

from agent.tools.warehouse_sql import run_sql

KEY_EXPR = {
    "cn_core.tele_process_instance_call_logs": "dialer_code || ':' || call_session_id",  # every status row of the session shares this key
    "cn_core.communication_dashboard_t": "id::text", "cn_core.digital_template": "template_id::text",
    "compliance.customer_consent": "consent_id::text", "compliance.call_recording": "recording_id::text",
    "compliance.call_transcript_segment": "segment_id::text", "compliance.calling_policy_rule": "rule_id::text",
    "compliance.holiday_calendar": "holiday_id::text", "compliance.notice": "notice_id::text",
    "compliance.collector_certification": "cert_id::text", "uamdb.users": "user_id::text", "compliance.collector_status": "status_id::text", "compliance.registered_cli": "cli_id::text",
}
CHUNK = 400


def verify_records(refs: set[tuple[str, str]]) -> tuple[int, list[dict]]:
    """Read each (source_table, record_key) back from its source table through the warehouse SQL tool.
    Returns (how many were found, [{source_table, record_key} that were not found or name an unknown table])."""
    by_table: dict[str, list[str]] = {}
    missing: list[dict] = []
    for table, key in refs:
        if table in KEY_EXPR:
            by_table.setdefault(table, []).append(key)
        else:
            missing.append({"source_table": table, "record_key": key, "why": "unknown source table"})
    found = 0
    for table, keys in by_table.items():
        expr = KEY_EXPR[table]  # a fixed expression from the table above, never text from a request
        got: set[str] = set()
        for i in range(0, len(keys), CHUNK):
            out = run_sql(f"SELECT DISTINCT {expr} AS k FROM {table} WHERE {expr} = ANY(%(keys)s)", {"keys": keys[i:i + CHUNK]}, max_rows=CHUNK)
            got |= {str(r["k"]) for r in out["rows"]}
        found += len(got)
        missing += [{"source_table": table, "record_key": k, "why": "not found in the source table"} for k in keys if k not in got]
    return found, missing
