"""Mirrored call sessions: the same call logged by both dialers, linked by an authoritative cross-reference."""
from __future__ import annotations

from agent.core.toolkit import tool
from agent.tools._common import query


@tool("session_mirrors", sources=("Call-session cross-reference",))
def get_mirror_keys(session_keys: list[str]) -> dict[str, list[str]]:
    """For each dialer-qualified session key, the keys of the sessions the other dialer logged for the same call. A session with
    no mirror is absent from the result. Evidence held under a mirror (a recording, a transcript) is evidence about the same call."""
    if not session_keys:
        return {}
    out: dict[str, list[str]] = {}
    for r in query("SELECT session_key, mirror_key FROM staging.session_mirrors WHERE session_key = ANY(%s)", (list(session_keys),)):
        out.setdefault(r["session_key"], []).append(r["mirror_key"])
    return out
