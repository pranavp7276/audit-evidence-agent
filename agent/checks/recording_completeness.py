from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_contacts, get_recordings


class RecordingCompletenessCheck(BaseCheck):
    """Every connected call in a series has a recording.

    Test per call (subject_ref = call id): gap if the contact log shows a connected call and the
    recording store has nothing for it. Cite the contact log row for the missing call."""

    check_type = "recording_completeness"

    def evaluate(self, account_id: str) -> list[Finding]:
        recorded = {r["contact_id"]: r for r in get_recordings(account_id)}
        gaps, oks = [], []
        for c in get_contacts(account_id, channel="call"):
            if c["outcome"] != "connected":
                continue
            call = cite(c, ("outcome", "contact_ts_src"))
            if c["contact_id"] in recorded:
                oks.append((c["contact_id"],
                    f"Connected call {c['contact_id']} has recording {recorded[c['contact_id']]['recording_id']}.",
                            [call, cite(recorded[c["contact_id"]], ("duration_sec", "recorded_ts_src"), "supporting")]))
            else:
                gaps.append((c["contact_id"],
                    f"Connected call {c['contact_id']} has no recording in the recording store.", [call]))
        return self.assemble(account_id, gaps, oks, [], "No connected calls in the contact log to test.")
