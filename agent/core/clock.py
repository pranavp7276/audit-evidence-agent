"""The zone every rule is stated in: D12 hours and limits, the certification register and audit periods use India time (docs/decisions.md D-009)."""
from zoneinfo import ZoneInfo

RULE_TZ = ZoneInfo("Asia/Kolkata")
