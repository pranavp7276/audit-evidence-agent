"""Turn an audit request (PDF or email text) into a list of CheckSpecs.

This is the main LLM step. Output must validate against agent.contracts.CheckSpec; anything
that does not validate is rejected, not patched. Compound questions become several checks
sharing a question_ref (Q3 -> Q3a, Q3b). A question that maps to no known check type becomes
check_type=OTHER so it still appears in the response as unanswered, never silently dropped.
"""
from __future__ import annotations

from pathlib import Path

from agent.contracts import CheckSpec, Request


def read_request(path: str | Path, request_id: str) -> Request:
    """Read a PDF or text/email file into a Request (text only; severity scale parsed later)."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        raise NotImplementedError("TODO(owner): PDF text extraction")
    source = "email" if path.suffix.lower() in (".eml", ".msg") else "text"
    return Request(request_id=request_id, source=source, path=str(path), text=path.read_text())


def parse_checks(request: Request) -> tuple[list[CheckSpec], list[str]]:
    """Return (checks, severity_scale). TODO(owner): LLM call with structured JSON output."""
    raise NotImplementedError
