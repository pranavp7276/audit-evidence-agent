"""Recording and transcript store: was each call recorded, and what was said."""
from __future__ import annotations

from datetime import datetime


def get_recordings(account_id: str, start: datetime | None = None,
                   end: datetime | None = None) -> list[dict]:
    """Recording metadata for an account. A call with no row here is a missing recording.

    TODO(owner): implement over the staging view for recordings.
    """
    raise NotImplementedError


def get_transcript(call_id: str) -> dict | None:
    """Transcript for one call, with utterance timestamps, used to test verification before
    disclosure. Returns None if there is no transcript (that is cannot_determine, not a pass).

    TODO(owner): implement.
    """
    raise NotImplementedError
