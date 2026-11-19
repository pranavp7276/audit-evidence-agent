from __future__ import annotations

from agent.checks.base import RULE_TZ, BaseCheck, cite, mask
from agent.core.contracts import Finding
from agent.tools import get_calls, get_registered_clis

_CALL = ("dialer_code", "process_mode", "agency_code", "started_ts_src", "started_ts_src_tz")
_REG = ("cli_id", "agency_code", "purpose", "valid_from", "valid_to")


class CallerIdRegisteredCheck(BaseCheck):
    """Every outbound call was placed from a number registered to the agency on the call date, never from a personal mobile (catalog CLI-01).

    Test per call session (subject_ref = dialer:session id): the number the call was placed from (the caller ID in the call log)
    is looked up in the agency's registered caller ID list. The call date is the IST date; valid_from and valid_to are inclusive.
      evidenced  the number is registered to the collector's agency and the registration covers the date
      gap        the number was never registered to the agency, or was registered only from a later date
      cannot_determine  the call log carries no caller number, or the collector's agency is unknown"""

    check_type = "caller_id_registered"
    tools = ('contact_log', 'caller_id_registry')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks, unknown = [], [], []
        for c in get_calls(account_id, *self.window, attempts_only=True):
            k, day, cli, agency = c["session_key"], c["started_ts_utc"].astimezone(RULE_TZ).date(), c["cli_number"], c["agency_code"]
            if not cli:
                unknown.append((k, f"Call {k}: the call log carries no caller number, so it cannot be checked against the registered list."))
                continue
            if not agency:
                unknown.append((k, f"Call {k}: the collector's agency is unknown, so the registered list to check against is unknown."))
                continue
            regs = get_registered_clis(agency, cli)
            valid = [r for r in regs if r["valid_from"] <= day and (r["valid_to"] is None or day <= r["valid_to"])]
            call = cite(c, _CALL)
            if valid:
                oks.append((k, f"Call {k} was placed from {mask(cli)}, registered to {agency}.", [call, cite(valid[0], _REG, "supporting")]))
            elif later := [r for r in regs if r["valid_from"] > day]:
                gaps.append((k, f"Call {k} on {day} was placed from {mask(cli)}, which was registered to {agency} only from {later[0]['valid_from']}.", [call, cite(later[0], _REG, "supporting")]))
            elif regs:
                gaps.append((k, f"Call {k} on {day} was placed from {mask(cli)}, whose registration to {agency} ended on {regs[-1]['valid_to']}.", [call, cite(regs[-1], _REG, "supporting")]))
            else:
                gaps.append((k, f"Call {k} on {day} was placed from {mask(cli)}, which is not on {agency}'s registered caller ID list.", [call]))
        return self.assemble(account_id, gaps, oks, unknown, "No outbound call attempts in the period to test.")
