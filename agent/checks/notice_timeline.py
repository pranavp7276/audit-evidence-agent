from __future__ import annotations

from datetime import date

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_notices
from agent.tools.dispatch_tracker import add_business_days, business_days_between
from agent.tools.policy import rule_at, rule_int_at

_NOTICE = ("notice_type", "trigger_date", "dispatch_date", "served_date")
_RULE = ("rule_key", "rule_value", "unit", "effective_from", "effective_to")


class NoticeTimelineCheck(BaseCheck):
    """Each notice was dispatched, and served, within the business days D12 allows from its trigger date.

    Test per notice (subject_ref = notice id), using the rules in force on the trigger date: count business days
    (Mon-Fri, national holidays excluded; day N is inside the limit) from the trigger to dispatch and to service.
    gap if dispatch or service is late, or has not happened although its deadline has passed.
    cannot_determine if a deadline has not passed yet. Cite the notice, the rules and the holidays skipped.
    Notices are tested over their own history, not only the audit period (docs/decisions.md D-014)."""

    check_type = "notice_timeline"
    tools = ('dispatch_tracker', 'policy_rules')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        today = date.today()
        gaps, oks, unknown = [], [], []
        for n in get_notices(account_id):
            trig = n["trigger_date"]
            d_rule, s_rule = rule_at("notice_dispatch_sla_business_days", trig), rule_at("notice_service_sla_business_days", trig)
            d_due, d_skip = add_business_days(trig, rule_int_at("notice_dispatch_sla_business_days", trig))
            s_due, s_skip = add_business_days(trig, rule_int_at("notice_service_sla_business_days", trig))
            problems, pending = [], []
            for label, actual, due in (("dispatched", n["dispatch_date"], d_due), ("served", n["served_date"], s_due)):
                if actual is None:
                    (problems if due < today else pending).append(f"not {label}{' although it was due by ' + str(due) if due < today else ' yet (due ' + str(due) + ')'}")
                elif actual > due:
                    problems.append(f"{label} on {actual}, {business_days_between(trig, actual)} business days after the trigger; due by {due}")
            cites = [cite(n, _NOTICE), cite(d_rule, _RULE, "supporting"), cite(s_rule, _RULE, "supporting"),
                     *(cite(h, ("holiday_name", "scope"), "supporting") for h in {h["record_key"]: h for h in d_skip + s_skip}.values())]
            ref = f"Notice {n['notice_id']} (triggered {trig})"
            if problems:
                gaps.append((n["notice_id"], f"{ref}: " + "; ".join(problems) + ".", cites))
            elif pending:
                unknown.append((n["notice_id"], f"{ref}: " + "; ".join(pending) + ", so it cannot be judged yet."))
            else:
                oks.append((n["notice_id"], f"{ref} was dispatched by {n['dispatch_date']} (due {d_due}) and served by {n['served_date']} (due {s_due}).", cites))
        return self.assemble(account_id, gaps, oks, unknown, "No notices on file for this account to test.")
