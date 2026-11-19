from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class NoticeTimelineCheck(BaseCheck):
    """Notices were served within the required timeline.

    Test per notice (subject_ref = notice id): count days per the rule in the request or policy,
    excluding holidays from the national + applicable state calendar if the rule says working days.
    gap if served late or never served. Cite the dispatch row and the holiday rows used."""

    check_type = "notice_timeline"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
