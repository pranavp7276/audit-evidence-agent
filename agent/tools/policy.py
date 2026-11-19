"""D12 policy rules, effective-dated: calling window, daily attempt cap and notice timelines. Never hard-code these."""
from __future__ import annotations

from datetime import date, time
from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=1)
def get_rules() -> tuple[dict, ...]:
    """Every D12 rule row with citation fields; a rule key can have several rows with different effective dates."""
    rows = query("SELECT * FROM staging.policy_rules ORDER BY rule_key, effective_from")
    return tuple(with_citation(r, "D12", "compliance.calling_policy_rule", "rule_id") for r in rows)


def rule_at(rule_key: str, day: date) -> dict:
    """The rule in force on a date: rule_value, unit, counting_unit and counting_rule, with citation fields."""
    for r in get_rules():
        if r["rule_key"] == rule_key and r["effective_from"] <= day and (r["effective_to"] is None or day < r["effective_to"]):
            return r
    raise LookupError(f"No D12 rule '{rule_key}' in force on {day}")


def rule_time_at(rule_key: str, day: date) -> time:
    return time.fromisoformat(rule_at(rule_key, day)["rule_value"])


def rule_int_at(rule_key: str, day: date) -> int:
    return int(rule_at(rule_key, day)["rule_value"])
