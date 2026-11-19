from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class RecordingCompletenessCheck(BaseCheck):
    """Every connected call in a series has a recording.

    Test per call (subject_ref = call id): gap if the contact log shows a connected call and the
    recording store has nothing for it. Cite the contact log row for the missing call."""

    check_type = "recording_completeness"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
