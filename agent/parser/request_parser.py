"""Turn an audit request (PDF or email text) into a list of CheckSpecs.

This is the main LLM step. Output must validate against agent.contracts.CheckSpec; anything
that does not validate is rejected, not patched. Compound questions become several checks
sharing a question_ref (Q3 -> Q3a, Q3b). A question that maps to no known check type becomes
check_type=OTHER so it still appears in the response as unanswered, never silently dropped.

With ANTHROPIC_API_KEY set the questions are interpreted by Claude. Without a key a keyword
fallback is used (docs/decisions.md D-012) so the pipeline can still run; it only knows the
seven check types and the "Q<n>." question layout.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from agent.contracts import CheckSpec, CheckType, Request, SourceSystem

_QUESTION = re.compile(r"^\s*(Q\d+)\s*[.:)]\s*(.+?)\s*$", re.MULTILINE)
_SEVERITY_LINE = re.compile(r"^\s*([A-Za-z][\w ]*?)\s+[-:]\s+.*$")
_ACCOUNT_BLOCK = re.compile(r"sampled accounts[^\n]*:\s*(.+)\Z", re.IGNORECASE | re.DOTALL)

_KEYWORDS: list[tuple[CheckType, tuple[str, ...]]] = [
    (CheckType.CONSENT_BEFORE_CONTACT, ("consent",)),
    (CheckType.CALLING_HOURS, ("hours", "time of day")),
    (CheckType.CALLING_FREQUENCY, ("frequen", "more often", "per day")),
    (CheckType.VERIFICATION_BEFORE_DISCLOSURE, ("verif", "identity")),
    (CheckType.NOTICE_TIMELINE, ("notice",)),
    (CheckType.AGENT_CERTIFICATION, ("certif",)),
    (CheckType.RECORDING_COMPLETENESS, ("recording",)),
]
_SOURCES: dict[CheckType, list[SourceSystem]] = {
    CheckType.CONSENT_BEFORE_CONTACT: [SourceSystem.D4, SourceSystem.D5],
    CheckType.CALLING_HOURS: [SourceSystem.D4, SourceSystem.D12],
    CheckType.CALLING_FREQUENCY: [SourceSystem.D4, SourceSystem.D12],
    CheckType.VERIFICATION_BEFORE_DISCLOSURE: [SourceSystem.D4, SourceSystem.D11],
    CheckType.NOTICE_TIMELINE: [SourceSystem.NOTICE_DISPATCH, SourceSystem.D12, SourceSystem.HOLIDAY_CALENDAR],
    CheckType.AGENT_CERTIFICATION: [SourceSystem.D4, SourceSystem.CERT_REGISTER],
    CheckType.RECORDING_COMPLETENESS: [SourceSystem.D4, SourceSystem.D10],
    CheckType.OTHER: [],
}


def read_request(path: str | Path, request_id: str) -> Request:
    """Read a PDF or text/email file into a Request (text only; severity scale parsed later)."""
    path = Path(path)
    if path.suffix.lower() == ".pdf":
        raise NotImplementedError("TODO(owner): PDF text extraction")
    source = "email" if path.suffix.lower() in (".eml", ".msg") else "text"
    return Request(request_id=request_id, source=source, path=str(path), text=path.read_text(encoding="utf-8"))


def extract_sample_accounts(text: str) -> list[str]:
    """Account ids listed after a 'Sampled accounts:' heading, in order, without duplicates."""
    m = _ACCOUNT_BLOCK.search(text)
    return list(dict.fromkeys(t for t in re.split(r"[,\s]+", m.group(1)) if t)) if m else []


def _severity_by_question(text: str) -> tuple[list[str], dict[str, str]]:
    """The scale labels (most severe first, as written) and which label each Q<n> carries."""
    labels, by_q = [], {}
    in_block = False
    for line in text.splitlines():
        if re.match(r"\s*severity scale", line, re.IGNORECASE):
            in_block = True
            continue
        if not in_block:
            continue
        if not line.strip():
            if labels:
                break
            continue
        m = _SEVERITY_LINE.match(line)
        if not m:
            break
        labels.append(m.group(1).strip())
        for q in re.findall(r"Q\d+", line):
            by_q[q] = labels[-1]
    return labels, by_q


def _parse_fallback(request: Request) -> tuple[list[CheckSpec], list[str]]:
    scale, by_q = _severity_by_question(request.text)
    checks: list[CheckSpec] = []
    for ref, question in _QUESTION.findall(request.text):
        lowered = question.lower()
        types = [t for t, words in _KEYWORDS if any(w in lowered for w in words)] or [CheckType.OTHER]
        for i, t in enumerate(types):
            checks.append(CheckSpec(
                check_id=ref if len(types) == 1 else f"{ref}{chr(97 + i)}", question_ref=ref, question_text=question,
                check_type=t, sample={"source": "request_text"},
                test={"severity": by_q.get(ref)} if by_q.get(ref) else {}, sources=_SOURCES[t]))
    return checks, scale


_PROMPT = """You split an audit request into checks. Return ONLY JSON:
{"severity_scale": [labels most severe first, exactly as written],
 "checks": [{"check_id": "Q3a", "question_ref": "Q3", "question_text": "<exact wording>",
             "check_type": one of %s,
             "test": {"severity": "<label that applies to this question, if the request gives one>"},
             "sources": [subset of %s]}]}
A compound question becomes several checks (Q3a, Q3b). A question that fits no type gets check_type "other".
Never drop a question. Do not judge pass or fail; that is done in code.

Request:
%s"""


def _parse_with_llm(request: Request) -> tuple[list[CheckSpec], list[str]]:
    import anthropic  # imported here so the fallback works without the SDK or a key

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("AGENT_MODEL", "claude-sonnet-4-6"), max_tokens=8000,
        messages=[{"role": "user", "content": _PROMPT % (
            [t.value for t in CheckType], [s.value for s in SourceSystem], request.text)}])
    raw = "".join(b.text for b in msg.content if b.type == "text")
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    checks = [CheckSpec(**{**c, "sample": {"source": "request_text"}}) for c in data["checks"]]
    return checks, list(data.get("severity_scale", []))


def parse_checks(request: Request) -> tuple[list[CheckSpec], list[str]]:
    """Return (checks, severity_scale)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return _parse_with_llm(request)
    print("ANTHROPIC_API_KEY is not set: using the keyword fallback parser (docs/decisions.md D-012).")
    return _parse_fallback(request)
