from __future__ import annotations

from collections import defaultdict

from agent.checks.base import RULE_TZ, BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_contacts
from agent.tools.policy import get_policy, policy_time, policy_value

_CALL_FIELDS = ("channel", "outcome", "contact_ts_src")
_RULE_FIELDS = ("policy_value", "unit", "note")


class CallingHoursCheck(BaseCheck):
    """Every call was placed within permitted hours. Limits come from D12, never hard-coded.

    Test per call (subject_ref = call id), in the time zone the D12 rule is defined in
    (see docs/decisions.md): evidenced if inside the window, gap if outside.
    Cite both the call record (D4) and the D12 rule row.
    """

    check_type = "calling_hours"

    def evaluate(self, account_id: str) -> list[Finding]:
        start, end = policy_time("calling_hours_start"), policy_time("calling_hours_end")
        rules = [cite(get_policy()[k], _RULE_FIELDS, "supporting") for k in ("calling_hours_start", "calling_hours_end")]
        gaps, oks = [], []
        for c in get_contacts(account_id, *self.window, channel="call"):
            local = c["contact_ts_utc"].astimezone(RULE_TZ)
            inside = start <= local.time().replace(tzinfo=None) < end
            evt = (c["contact_id"],
                   f"Call {c['contact_id']} at {local:%Y-%m-%d %H:%M} local was {'inside' if inside else 'outside'} "
                   f"the permitted {start:%H:%M}-{end:%H:%M}.", [cite(c, _CALL_FIELDS), *rules])
            (oks if inside else gaps).append(evt)
        return self.assemble(account_id, gaps, oks, [], "No calls in the contact log to test.")


class CallingFrequencyCheck(BaseCheck):
    """Calls per account per period stayed within the D12 limit.

    Test per account per period (subject_ref = period, e.g. '2026-05-14' or '2026-W20'):
    gap if attempts or connects exceed the D12 limit. Cite every call in the breaching
    period plus the D12 rule. Day boundaries are computed in the rule's time zone.
    """

    check_type = "calling_frequency"

    def evaluate(self, account_id: str) -> list[Finding]:
        limit = int(policy_value("max_calls_per_day"))
        rule = cite(get_policy()["max_calls_per_day"], _RULE_FIELDS, "supporting")
        by_day = defaultdict(list)
        for c in get_contacts(account_id, *self.window, channel="call"):
            by_day[c["contact_ts_utc"].astimezone(RULE_TZ).date()].append(c)
        gaps, oks = [], []
        for day, calls in sorted(by_day.items()):
            evt = (day.isoformat(), f"{len(calls)} call attempt(s) on {day}; the limit is {limit} per day.",
                   [*(cite(c, _CALL_FIELDS) for c in calls), rule])
            (gaps if len(calls) > limit else oks).append(evt)
        return self.assemble(account_id, gaps, oks, [], "No calls in the contact log to test.")
