from __future__ import annotations

from agent.checks.base import RULE_TZ, BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_calls, get_certifications, get_collector

_CALL = ("dialer_code", "employee_code", "started_ts_src", "started_ts_src_tz")
_CERT = ("employee_code", "certification", "certificate_no", "valid_from", "valid_to")


class AgentCertificationCheck(BaseCheck):
    """The collector held a valid certificate on the date of each outbound call they made.

    Test per call session (subject_ref = dialer:session id): the contact log names the collector by user id; the
    certification register uses the employee code, so the call is joined through the user record. The call date is the
    IST date. evidenced if some certificate has valid_from <= date <= valid_to (both inclusive).
    gap if the certificate expired, had not started, or the register has none for that employee code.
    cannot_determine if the collector has no employee code, so they cannot be matched to the register.
    Cite the call and the certificate rows (or the roster row if there is no certificate)."""

    check_type = "agent_certification"

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks, unknown = [], [], []
        for c in get_calls(account_id, *self.window, attempts_only=True):
            k, day, code = c["session_key"], c["started_ts_utc"].astimezone(RULE_TZ).date(), c["employee_code"]
            if not code:
                unknown.append((k, f"Call {k}: the collector (user {c['collector_user_id']}) has no employee code, so they cannot be matched to the certification register."))
                continue
            certs = get_certifications(code)
            valid = [x for x in certs if x["valid_from"] <= day <= x["valid_to"]]
            call = cite(c, _CALL)
            if valid:
                oks.append((k, f"Collector {code} was certified on {day} for call {k}.", [call, cite(valid[0], _CERT, "supporting")]))
            else:
                roster = get_collector(c["collector_user_id"])
                support = ([cite(x, _CERT, "supporting") for x in certs] or ([cite(roster, ("employee_code", "agency", "role_name"), "supporting")] if roster else []))
                why = "its certificate was not valid on that date" if certs else "the register has no certificate for them"
                gaps.append((k, f"Collector {code} held no valid certificate on {day} for call {k}: {why}.", [call, *support]))
        return self.assemble(account_id, gaps, oks, unknown, "No outbound call attempts in the period to test.")
