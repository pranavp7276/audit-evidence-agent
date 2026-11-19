from __future__ import annotations

from agent.checks.base import RULE_TZ, BaseCheck, cite
from agent.core.contracts import Finding
from agent.tools import get_calls, get_collector_status

_CALL = ("dialer_code", "employee_code", "started_ts_src", "started_ts_src_tz")
_STATUS = ("employee_code", "status", "valid_from", "valid_to")


def _covers(row: dict, day) -> bool:
    return row["valid_from"] <= day and (row["valid_to"] is None or day <= row["valid_to"])


class CollectorActiveCheck(BaseCheck):
    """The collector who made each call was an active collector on the date of the call (catalog AGT-01).

    Test per call session (subject_ref = dialer:session id): the contact log names the collector by user id and the status history by
    employee code, so the call is joined through the user record. The call date is the IST date.
      evidenced  an ACTIVE status covers the date (valid_from and valid_to inclusive; valid_to empty while it still holds)
      gap        the status covering the date is TERMINATED or INACTIVE, or no status covers it
      cannot_determine  the collector has no employee code, or no status history exists for it"""

    check_type = "collector_active"
    tools = ('contact_log', 'collector_status')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks, unknown = [], [], []
        for c in get_calls(account_id, *self.window, attempts_only=True):
            k, day, code = c["session_key"], c["started_ts_utc"].astimezone(RULE_TZ).date(), c["employee_code"]
            if not code:
                unknown.append((k, f"Call {k}: the collector (user {c['collector_user_id']}) has no employee code, so their status cannot be looked up."))
                continue
            history = get_collector_status(code)
            if not history:
                unknown.append((k, f"Call {k}: no status history is recorded for collector {code}."))
                continue
            call = cite(c, _CALL)
            now = [h for h in history if _covers(h, day)]
            if any(h["status"] == "ACTIVE" for h in now):
                oks.append((k, f"Collector {code} was active on {day} for call {k}.", [call, cite(next(h for h in now if h["status"] == "ACTIVE"), _STATUS, "supporting")]))
                continue
            if now and now[0]["status"] == "TERMINATED":
                state = f"terminated since {now[0]['valid_from']}"
            elif now:
                state = f"inactive from {now[0]['valid_from']} to {now[0]['valid_to']}"
            else:
                state = "without an active status on record"
            gaps.append((k, f"Collector {code} was {state} on {day}, when call {k} was placed.", [call, *(cite(h, _STATUS, "supporting") for h in (now or history[-1:]))]))
        return self.assemble(account_id, gaps, oks, unknown, "No outbound call attempts in the period to test.")
