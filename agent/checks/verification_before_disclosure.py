from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_calls, get_recordings, get_transcripts

_CALL = ("dialer_code", "direction", "process_mode", "statuses", "started_ts_src", "started_ts_src_tz")
_SEG = ("seq", "start_offset_sec", "speaker", "tag")
_REC = ("storage_status", "note", "checked_ts_src")


class VerificationBeforeDisclosureCheck(BaseCheck):
    """Identity was verified before dues were first disclosed on a connected outbound call.

    Test per connected call (subject_ref = dialer:session id), from the recording's transcript offsets:
      evidenced  a passed identity check at an earlier offset than the first disclosure of dues
      gap        disclosure before the identity check, only a failed check, or no identity check at all
      cannot_determine  the recording could not be read or is missing, there is no transcript, the identity step is unclear,
                        or the pass is at exactly the disclosure offset (D-011): no claim either way
    A call where dues were never disclosed has nothing to test. Cite the call, the recording status and the segments."""

    check_type = "verification_before_disclosure"
    tools = ('contact_log', 'recording_store', 'transcript_store')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        calls = [c for c in get_calls(account_id, *self.window, attempts_only=True) if c["connected"]]
        keys = [c["session_key"] for c in calls]
        recs, transcripts = get_recordings(keys), get_transcripts(keys)
        gaps, oks, unknown = [], [], []
        for c in calls:
            k = c["session_key"]
            rec, segs = recs.get(k), transcripts.get(k, [])
            if rec is None or rec["storage_status"] != "AVAILABLE":
                state = rec["storage_status"] if rec else "no recording record"
                unknown.append((k, f"Call {k}: the recording is not available ({state}), so identity verification cannot be checked."))
                continue
            if not segs:
                unknown.append((k, f"Call {k} is recorded but has no transcript, so identity verification cannot be checked."))
                continue
            disclosures = [s for s in segs if s["tag"] == "DUES_DISCLOSURE"]
            if not disclosures:
                continue  # dues were never disclosed: nothing to verify
            first = min(float(s["start_offset_sec"]) for s in disclosures)
            first_seg = min(disclosures, key=lambda s: float(s["start_offset_sec"]))
            checks = [s for s in segs if s["tag"].startswith("IDENTITY_CHECK")]
            passed = [s for s in checks if s["tag"] == "IDENTITY_CHECK_PASS"]
            call = cite(c, _CALL)
            mirror = rec.get("via_mirror") or (segs[0].get("via_mirror") if segs else None)
            note = f" (evidence held by the mirrored session {mirror})" if mirror else ""
            support = [cite(rec, _REC, "supporting"), cite(first_seg, _SEG, "supporting"), *(cite(s, _SEG, "supporting") for s in checks)]
            if any(s["tag"] == "UNCLEAR" for s in segs) and not passed:
                unknown.append((k, f"Call {k}: the identity step is unclear in the transcript, so verification cannot be confirmed."))
            elif any(float(s["start_offset_sec"]) < first for s in passed):
                ok = min((s for s in passed if float(s["start_offset_sec"]) < first), key=lambda s: float(s["start_offset_sec"]))
                oks.append((k, f"Call {k}: identity verified at {float(ok['start_offset_sec']):.0f}s, before dues were disclosed at {first:.0f}s{note}.", [call, *support]))
            elif any(float(s["start_offset_sec"]) == first for s in passed):
                unknown.append((k, f"Call {k}: identity verification is at exactly the first disclosure offset; whether that is 'before' is not settled (D-011)."))
            else:
                why = (f"verified only at {min(float(s['start_offset_sec']) for s in passed):.0f}s, after the disclosure at {first:.0f}s" if passed
                       else "the identity check failed" if checks else "no identity check appears in the call")
                gaps.append((k, f"Call {k} disclosed dues at {first:.0f}s without prior identity verification: {why}{note}.", [call, *support]))
        return self.assemble(account_id, gaps, oks, unknown, "No connected outbound calls in the period to test.")
