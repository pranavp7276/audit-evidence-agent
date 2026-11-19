"""The caller IDs an agency may call from, with the dates each was registered for."""
from __future__ import annotations

from functools import lru_cache

from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@lru_cache(maxsize=8192)
def _registered(agency_code: str, cli_number: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.registered_clis WHERE agency_code = %s AND cli_number = %s ORDER BY valid_from", (agency_code, cli_number))
    return tuple(with_citation(r, "collector_roster", "compliance.registered_cli", "cli_id") for r in rows)


@tool("caller_id_registry", sources=("Registered caller IDs",))
def get_registered_clis(agency_code: str, cli_number: str) -> list[dict]:
    """The registrations of one number for one agency. Each row: cli_id, cli_number, agency_code, purpose, valid_from and valid_to
    (both inclusive dates; valid_to is empty while it still holds), plus citation fields. No rows means the number was never registered to that agency."""
    return list(_registered(agency_code, cli_number))
