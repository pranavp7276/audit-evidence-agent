from __future__ import annotations

from datetime import timedelta

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_notices
from agent.tools.dispatch_tracker import national_holidays
from agent.tools.policy import get_policy, policy_value


class NoticeTimelineCheck(BaseCheck):
    """Notices were served within the required timeline.

    Test per notice (subject_ref = notice id): count business days (Mon-Fri, national holidays
    excluded: docs/decisions.md D-010) from trigger date to service date against the D12 limit.
    gap if served late or never served. Cite the dispatch row and the holiday rows used."""

    check_type = "notice_timeline"

    def evaluate(self, account_id: str) -> list[Finding]:
        sla = int(policy_value("notice_sla_business_days"))
        rule = cite(get_policy()["notice_sla_business_days"], ("policy_value", "unit", "note"), "supporting")
        fields = ("notice_type", "trigger_date", "dispatch_date", "service_date")
        gaps, oks = [], []
        for n in get_notices(account_id):
            notice = cite(n, fields)
            if n["service_date"] is None:
                gaps.append((n["notice_id"], f"Notice {n['notice_id']} has no service date.", [notice, rule]))
                continue
            holidays = national_holidays(n["trigger_date"], n["service_date"])
            skip = {h["holiday_date"] for h in holidays}
            days = [n["trigger_date"] + timedelta(days=i) for i in range(1, (n["service_date"] - n["trigger_date"]).days + 1)]
            used = sum(1 for d in days if d.weekday() < 5 and d not in skip)
            evt = (n["notice_id"],
                f"Notice {n['notice_id']} was served {used} business day(s) after trigger; the limit is {sla}.",
                   [notice, rule, *(cite(h, ("holiday_name", "scope"), "supporting") for h in holidays)])
            (gaps if used > sla else oks).append(evt)
        return self.assemble(account_id, gaps, oks, [], "No notices on file for this account to test.")
