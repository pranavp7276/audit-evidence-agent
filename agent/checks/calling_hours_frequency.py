from __future__ import annotations

from collections import defaultdict

from agent.checks.base import RULE_TZ, BaseCheck, cite, mask
from agent.contracts import Finding
from agent.tools import get_calls
from agent.tools.policy import rule_at, rule_int_at, rule_time_at

_CALL = ("dialer_code", "contact_no", "direction", "process_mode", "statuses", "started_ts_src", "started_ts_src_tz")
_RULE = ("rule_key", "institution_code", "rule_value", "unit", "counting_unit", "counting_rule", "effective_from", "effective_to")


class CallingHoursCheck(BaseCheck):
    """Every outbound call attempt started inside the calling window in force on that date. D12 supplies the window.

    Test per call session (subject_ref = dialer:session id). The dialer's own timestamp is converted to the policy's
    zone (IST) first, then compared with the window rule effective on the local call date (the rule can change over
    time). A session with several status rows is one call; a call mirrored in both dialers counts once; inbound calls
    and system failures are not attempts. Cite the call and the rule rows used."""

    check_type = "calling_hours"

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks = [], []
        for s in get_calls(account_id, *self.window, attempts_only=True):
            local = s["started_ts_utc"].astimezone(RULE_TZ)
            day = local.date()
            lender = s["institution_code"]
            lo, hi = rule_time_at("calling_window_start", day, lender), rule_time_at("calling_window_end", day, lender)
            inside = lo <= local.time().replace(tzinfo=None) < hi
            rules = [cite(rule_at("calling_window_start", day, lender), _RULE, "supporting"), cite(rule_at("calling_window_end", day, lender), _RULE, "supporting")]
            evt = (s["session_key"],
                   f"Call {s['session_key']} started {local:%Y-%m-%d %H:%M:%S} IST (logged {s['started_ts_src']} {s['started_ts_src_tz']}), "
                   f"{'inside' if inside else 'outside'} the permitted {lo:%H:%M}-{hi:%H:%M} on that date.", [cite(s, _CALL), *rules])
            (oks if inside else gaps).append(evt)
        return self.assemble(account_id, gaps, oks, [], "No outbound call attempts in the period to test.")


class CallingFrequencyCheck(BaseCheck):
    """Call attempts to one contact number on one IST calendar day stayed within the D12 cap in force that day.

    Test per contact number per day (subject_ref = 'contact number|date'). Counted: distinct outbound call sessions to
    that number, across both dialers and both modes (manual and campaign); a session's several status rows and a call
    mirrored in both dialers count once; system failures and inbound calls do not count. gap if the count exceeds the
    cap: the first session past the cap is cited as the primary record, the rest as supporting, with the rule."""

    check_type = "calling_frequency"

    def evaluate(self, account_id: str) -> list[Finding]:
        by_day = defaultdict(list)
        for s in get_calls(account_id, *self.window, attempts_only=True):
            by_day[(s["contact_no"], s["started_ts_utc"].astimezone(RULE_TZ).date())].append(s)
        duplicates = defaultdict(int)
        for s in get_calls(account_id, *self.window, include_duplicates=True):
            if s["is_mirror_duplicate"]:
                duplicates[(s["contact_no"], s["started_ts_utc"].astimezone(RULE_TZ).date())] += 1
        gaps, oks = [], []
        for (contact, day), calls in sorted(by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            lender = calls[0]["institution_code"]
            cap = rule_int_at("max_attempts_per_contact_per_day", day, lender)
            rule = cite(rule_at("max_attempts_per_contact_per_day", day, lender), _RULE, "supporting")
            n, dup = len(calls), duplicates.get((contact, day), 0)
            note = f" ({dup} mirrored duplicate(s) counted once)" if dup else ""
            if n > cap:
                over = calls[cap]  # the first attempt past the cap
                others = [c for c in calls if c is not over]
                evt = (f"{contact}|{day}", f"{n} eligible attempts to {mask(contact)} on {day} against a cap of {cap}{note}; "
                       f"call {over['session_key']} was the one that exceeded it.",
                       [cite(over, _CALL), *(cite(c, _CALL, "supporting") for c in others), rule])
                gaps.append(evt)
            else:
                oks.append((f"{contact}|{day}", f"{n} eligible attempt(s) to {mask(contact)} on {day}; the cap is {cap}{note}.",
                            [*(cite(c, _CALL) for c in calls), rule]))
        return self.assemble(account_id, gaps, oks, [], "No outbound call attempts in the period to test.")
