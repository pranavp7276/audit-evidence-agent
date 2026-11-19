"""The seven tools the problem statement says the agent must call.

Each tool is a plain Python function with a typed signature and a docstring the LLM sees.
Tools read only from staging.* (never raw.* directly, never audit.*), through a read-only
connection, and return records that already carry what a Citation needs:
source_system, source_table, record_key, the UTC timestamp and the original timestamp.
"""
from agent.tools.certification_register import get_certifications
from agent.tools.consent_registry import get_consents
from agent.tools.contact_log import get_contacts
from agent.tools.dispatch_tracker import get_notices
from agent.tools.recording_store import get_recordings, get_transcript
from agent.tools.template_registry import get_template
from agent.tools.warehouse_sql import run_sql

TOOLS = {
    "warehouse_sql": run_sql,
    "contact_log": get_contacts,
    "recording_store": get_recordings,
    "transcript_store": get_transcript,
    "consent_registry": get_consents,
    "template_registry": get_template,
    "dispatch_tracker": get_notices,
    "certification_register": get_certifications,
}

__all__ = ["TOOLS"]
