"""The tool registry. Every tool the agent can call is a plain function wrapped with @tool: it is registered with its name, sources and
description (for the planner and the model), and every call is timed, sized and attributed to the check that made it.

Tools read the staging views only, through the read-only role (docs/decisions.md). A tool never decides a result.
"""
from __future__ import annotations

import functools
import time
from collections.abc import Callable
from dataclasses import dataclass

from agent.runtime.context import current_check, current_trace


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    fn: Callable
    sources: tuple[str, ...] = ()
    read_only: bool = True


REGISTRY: dict[str, ToolSpec] = {}


def _size(out) -> int:
    if isinstance(out, (list, tuple, dict, set)):
        return len(out)
    return 1 if out else 0


def tool(name: str, sources: tuple[str, ...] = (), read_only: bool = True):
    """Register a function as an agent tool and trace its calls."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            trace, t0 = current_trace.get(), time.perf_counter()
            try:
                out = fn(*args, **kwargs)
            except Exception as exc:
                if trace:
                    trace.tool_call(current_check.get(), name, 0, (time.perf_counter() - t0) * 1000, error=type(exc).__name__)
                raise
            if trace:
                trace.tool_call(current_check.get(), name, _size(out), (time.perf_counter() - t0) * 1000)
            return out
        doc = (fn.__doc__ or "").strip().split("\n\n")[0].replace("\n", " ")
        spec = ToolSpec(name=name, description=doc, fn=wrapper, sources=sources, read_only=read_only)
        REGISTRY[name] = spec
        wrapper.spec = spec  # type: ignore[attr-defined]
        return wrapper
    return deco
