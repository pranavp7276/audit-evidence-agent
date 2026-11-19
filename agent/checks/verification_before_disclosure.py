from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class VerificationBeforeDisclosureCheck(BaseCheck):
    """Identity was verified before any dues were disclosed on the call.

    Test per call (subject_ref = call id), from the transcript and verification records:
      evidenced  verification event precedes the first disclosure of amount or dues
      gap        disclosure before verification, or no verification at all
      cannot_determine  no transcript / recording for the call (also flagged by
                        recording_completeness), so no claim either way"""

    check_type = "verification_before_disclosure"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
