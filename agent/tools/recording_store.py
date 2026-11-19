"""Recording and transcript store: whether each call was recorded, retrieval status, and what was said."""
from __future__ import annotations

from functools import lru_cache

from agent.core.context import alt_evidence
from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _recordings(session_keys: tuple[str, ...]) -> dict[str, dict]:
    rows = query("SELECT * FROM staging.recordings WHERE session_key = ANY(%s)", (list(session_keys),)) if session_keys else []
    return {r["session_key"]: with_citation(r, "recording_store", "compliance.call_recording", "recording_id", "checked_ts") for r in rows}


@tool("recording_store", sources=("Recording store",))
def get_recordings(session_keys: list[str]) -> dict[str, dict]:
    """Recording status per dialer-qualified session key: storage_status is AVAILABLE, NOT_FOUND (the store has no
    recording) or RETRIEVAL_FAILED (the store could not be read, so nothing can be concluded), with a note.
    A session with no row at all has no recording record. When the investigator has found mirrored sessions (the same call logged by
    the other dialer), a usable recording under a mirror is returned for the session, marked `via_mirror`, with the session's own status
    kept in `own_status`."""
    base = _recordings(tuple(session_keys))
    alt = alt_evidence.get()
    if not alt:
        return base
    out = dict(base)
    for k in session_keys:
        if alt.get(k) and (k not in out or out[k]["storage_status"] != "AVAILABLE"):
            for mk, row in _recordings(tuple(alt[k])).items():
                if row["storage_status"] == "AVAILABLE":
                    out[k] = {**row, "via_mirror": mk, "own_status": out[k]["storage_status"] if k in out else None}
                    break
    return out


@lru_cache(maxsize=4096)
def _transcripts(session_keys: tuple[str, ...]) -> dict[str, tuple[dict, ...]]:
    rows = query("SELECT * FROM staging.transcript_segments WHERE session_key = ANY(%s) ORDER BY session_key, seq", (list(session_keys),)) if session_keys else []
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["session_key"], []).append(with_citation(r, "transcript_store", "compliance.call_transcript_segment", "segment_id"))
    return {k: tuple(v) for k, v in out.items()}


@tool("transcript_store", sources=("Transcript store",))
def get_transcripts(session_keys: list[str]) -> dict[str, list[dict]]:
    """Transcript segments per session key, in order. Each segment: seq, start_offset_sec (seconds into the recording),
    speaker and tag (IDENTITY_CHECK_REQUEST, IDENTITY_CHECK_PASS, IDENTITY_CHECK_FAIL, DUES_DISCLOSURE, UNCLEAR, NONE)."""
    base = {k: list(v) for k, v in _transcripts(tuple(session_keys)).items()}
    alt = alt_evidence.get()
    if alt:
        for k in session_keys:
            if not base.get(k) and alt.get(k):
                for mk, segs in _transcripts(tuple(alt[k])).items():
                    if segs:
                        base[k] = [{**sg, "via_mirror": mk} for sg in segs]
                        break
    return base
