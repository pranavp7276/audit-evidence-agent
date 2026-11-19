from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class AgentCertificationCheck(BaseCheck):
    """The collector held a valid certificate on the date of each call they made.

    Test per call (subject_ref = call id): call date (in the zone the register uses) within
    [valid_from, valid_to] of some certificate for that collector_id.
    gap if expired / not yet valid / no certificate. Cite the call row and the certificate row
    (or the roster row, if no certificate exists)."""

    check_type = "agent_certification"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
