from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_calls, get_recordings

_CALL = ("dialer_code", "statuses", "started_ts_src", "started_ts_src_tz")
_REC = ("storage_status", "duration_sec", "note", "checked_ts_src")


class RecordingCompletenessCheck(BaseCheck):
    """Every connected outbound call has a recording in the recording store.

    Test per connected call (subject_ref = dialer:session id), using the retrieval status the store reports:
      evidenced  AVAILABLE
      gap        NOT_FOUND: the store confirms it holds no recording for the call
      cannot_determine  RETRIEVAL_FAILED (the store could not be read) or no status record: the recording may exist
    Cite the call and the recording status record."""

    check_type = "recording_completeness"
    tools = ('contact_log', 'recording_store')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        calls = [c for c in get_calls(account_id, *self.window, attempts_only=True) if c["connected"]]
        recs = get_recordings([c["session_key"] for c in calls])
        gaps, oks, unknown = [], [], []
        for c in calls:
            k, rec = c["session_key"], recs.get(c["session_key"])
            call = cite(c, _CALL)
            if rec is None:
                unknown.append((k, f"Connected call {k} has no recording status record, so its recording cannot be confirmed."))
            elif rec["storage_status"] == "AVAILABLE":
                via = (f", held by the mirrored session {rec['via_mirror']} (this session's own record shows "
                       f"{(rec.get('own_status') or 'no recording').lower().replace('_', ' ')})") if rec.get("via_mirror") else ""
                oks.append((k, f"Connected call {k} has a recording ({rec['duration_sec']} s){via}.", [call, cite(rec, _REC, "supporting")]))
            elif rec["storage_status"] == "NOT_FOUND":
                gaps.append((k, f"Connected call {k} has no recording: the recording store reports none for this session.", [call, cite(rec, _REC, "supporting")]))
            else:
                unknown.append((k, f"Connected call {k}: the recording store could not be read ({rec['storage_status']}), so the recording cannot be confirmed."))
        return self.assemble(account_id, gaps, oks, unknown, "No connected outbound calls in the period to test.")
