"""D12 policy limits: calling hours, daily call limit and notice SLA. Never hard-code these."""
from __future__ import annotations

from datetime import time
from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=1)
def get_policy() -> dict[str, dict]:
    """D12 rows keyed by policy_key, each with citation fields."""
    rows = query("SELECT * FROM staging.d12_policy ORDER BY source_row")
    return {r["policy_key"]: with_citation(r, "D12", "raw.d12", "policy_key") for r in rows}


def policy_value(key: str) -> str:
    return get_policy()[key]["policy_value"]


def policy_time(key: str) -> time:
    return time.fromisoformat(policy_value(key))
