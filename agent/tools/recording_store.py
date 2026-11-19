"""Recording and transcript store: whether each call was recorded, retrieval status, and what was said."""
from __future__ import annotations

from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _recordings(session_keys: tuple[str, ...]) -> dict[str, dict]:
    rows = query("SELECT * FROM staging.recordings WHERE session_key = ANY(%s)", (list(session_keys),)) if session_keys else []
    return {r["session_key"]: with_citation(r, "recording_store", "compliance.call_recording", "recording_id", "checked_ts") for r in rows}


def get_recordings(session_keys: list[str]) -> dict[str, dict]:
    """Recording status per dialer-qualified session key: storage_status is AVAILABLE, NOT_FOUND (the store has no
    recording) or RETRIEVAL_FAILED (the store could not be read, so nothing can be concluded), with a note.
    A session with no row at all has no recording record."""
    return _recordings(tuple(session_keys))


@lru_cache(maxsize=4096)
def _transcripts(session_keys: tuple[str, ...]) -> dict[str, tuple[dict, ...]]:
    rows = query("SELECT * FROM staging.transcript_segments WHERE session_key = ANY(%s) ORDER BY session_key, seq", (list(session_keys),)) if session_keys else []
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["session_key"], []).append(with_citation(r, "transcript_store", "compliance.call_transcript_segment", "segment_id"))
    return {k: tuple(v) for k, v in out.items()}


def get_transcripts(session_keys: list[str]) -> dict[str, list[dict]]:
    """Transcript segments per session key, in order. Each segment: seq, start_offset_sec (seconds into the recording),
    speaker and tag (IDENTITY_CHECK_REQUEST, IDENTITY_CHECK_PASS, IDENTITY_CHECK_FAIL, DUES_DISCLOSURE, UNCLEAR, NONE)."""
    return {k: list(v) for k, v in _transcripts(tuple(session_keys)).items()}
