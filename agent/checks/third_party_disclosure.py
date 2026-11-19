from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.core.contracts import Finding
from agent.tools import get_calls, get_recordings, get_transcripts

_CALL = ("dialer_code", "contact_type", "contact_source", "started_ts_src", "started_ts_src_tz")
_SEG = ("seq", "start_offset_sec", "speaker", "tag")
_REC = ("storage_status", "note", "checked_ts_src")


class ThirdPartyDisclosureCheck(BaseCheck):
    """No dues were disclosed on a call to a contact the borrower did not provide (catalog CNT-01).

    A reference contact (contact type REFERENCE in the borrower's contact list) is a person the borrower named, not the borrower.
    Test per connected outbound call (subject_ref = dialer:session id):
      evidenced  the number is one the borrower provided (primary or alternate), or it is a reference contact and the transcript shows no disclosure of dues
      gap        the number is a reference contact and the transcript shows dues disclosed (cite the disclosure turn)
      cannot_determine  the number is a reference contact and the recording or transcript is missing or unreadable
    Where a call is to a reference contact and the recording is missing, the transcript-based result is cannot determine (docs/decisions.md D-017)."""

    check_type = "third_party_disclosure"
    tools = ('contact_log', 'recording_store', 'transcript_store')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        calls = [c for c in get_calls(account_id, *self.window, attempts_only=True) if c["connected"]]
        refs = [c["session_key"] for c in calls if c["contact_type"] == "REFERENCE"]
        recs, transcripts = (get_recordings(refs), get_transcripts(refs)) if refs else ({}, {})
        gaps, oks, unknown = [], [], []
        for c in calls:
            k, call = c["session_key"], cite(c, _CALL)
            if c["contact_type"] != "REFERENCE":
                oks.append((k, f"Call {k} was to a number the borrower provided ({(c['contact_type'] or 'unknown').lower()}).", [call]))
                continue
            rec, segs = recs.get(k), transcripts.get(k, [])
            if rec is None or rec["storage_status"] != "AVAILABLE":
                unknown.append((k, f"Call {k} was to a reference contact, but the recording is not available ({rec['storage_status'] if rec else 'no recording record'}), so disclosure cannot be checked."))
            elif not segs:
                unknown.append((k, f"Call {k} was to a reference contact and is recorded, but has no transcript, so disclosure cannot be checked."))
            elif disclosed := [s for s in segs if s["tag"] == "DUES_DISCLOSURE"]:
                first = min(disclosed, key=lambda s: float(s["start_offset_sec"]))
                gaps.append((k, f"Call {k} was to a reference contact and disclosed dues at {float(first['start_offset_sec']):.0f}s.", [call, cite(rec, _REC, "supporting"), cite(first, _SEG, "supporting")]))
            else:
                oks.append((k, f"Call {k} was to a reference contact and the transcript shows no disclosure of dues.", [call, cite(rec, _REC, "supporting"), *(cite(s, _SEG, "supporting") for s in segs[:3])]))
        return self.assemble(account_id, gaps, oks, unknown, "No connected outbound calls in the period to test.")
