"""The seven tools the problem statement says the agent must call.

Each tool is a plain Python function with a typed signature and a docstring the LLM sees.
Tools read only from staging.* (never raw.* or cn_core.* directly, never audit.*), through a read-only
connection, and return records that already carry what a Citation needs:
source_system, source_table, record_key, the UTC timestamp and the original timestamp.
"""
from agent.tools.certification_register import get_certifications, get_collector
from agent.tools.consent_registry import get_consents
from agent.tools.contact_log import get_calls, get_messages
from agent.tools.dispatch_tracker import get_notices
from agent.tools.policy import rule_at
from agent.tools.recording_store import get_recordings, get_transcripts
from agent.tools.template_registry import get_template
from agent.tools.warehouse_sql import run_sql

TOOLS = {
    "warehouse_sql": run_sql,
    "contact_log": get_calls,
    "message_log": get_messages,
    "recording_store": get_recordings,
    "transcript_store": get_transcripts,
    "consent_registry": get_consents,
    "template_registry": get_template,
    "dispatch_tracker": get_notices,
    "certification_register": get_certifications,
    "policy_rules": rule_at,
}


def clear_caches() -> None:
    """Forget cached lookups so a new run sees the current database."""
    from agent.tools import (
        certification_register,
        consent_registry,
        contact_log,
        dispatch_tracker,
        policy,
        recording_store,
        template_registry,
    )
    for fn in (contact_log._calls, contact_log._messages, consent_registry._consents, recording_store._recordings, recording_store._transcripts,
               certification_register._certs, certification_register._collector, dispatch_tracker.get_holidays, policy.get_rules,
               template_registry.get_template):
        fn.cache_clear()


__all__ = ["TOOLS", "clear_caches", "get_calls", "get_certifications", "get_collector", "get_consents", "get_messages", "get_notices", "get_recordings", "get_template", "get_transcripts", "rule_at", "run_sql"]
