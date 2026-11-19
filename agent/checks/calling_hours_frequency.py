from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class CallingHoursCheck(BaseCheck):
    """Every call was placed within permitted hours. Limits come from D12, never hard-coded.

    Test per call (subject_ref = call id), in the time zone the D12 rule is defined in
    (see docs/decisions.md): evidenced if inside the window, gap if outside.
    Cite both the call record (D4) and the D12 rule row.
    """

    check_type = "calling_hours"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError


class CallingFrequencyCheck(BaseCheck):
    """Calls per account per period stayed within the D12 limit.

    Test per account per period (subject_ref = period, e.g. '2026-05-14' or '2026-W20'):
    gap if attempts or connects exceed the D12 limit. Cite every call in the breaching
    period plus the D12 rule. Day boundaries are computed in the rule's time zone.
    """

    check_type = "calling_frequency"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
