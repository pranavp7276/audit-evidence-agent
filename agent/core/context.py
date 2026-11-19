"""Run-scoped context, shared without threading arguments through every call.

current_trace   the Trace recording this run's steps (None outside a run)
current_check   the check being evaluated, so tool calls are attributed to it
alt_evidence    session key -> mirrored session keys the investigator wants tools to also consult
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.core.trace import Trace

current_trace: ContextVar[Trace | None] = ContextVar("current_trace", default=None)
current_check: ContextVar[str | None] = ContextVar("current_check", default=None)
alt_evidence: ContextVar[dict[str, list[str]] | None] = ContextVar("alt_evidence", default=None)
