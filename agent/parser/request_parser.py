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
from datetime import date, timedelta
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
    CheckType.CONSENT_BEFORE_CONTACT: [SourceSystem.CONTACT_LOG, SourceSystem.CONSENT_REGISTRY, SourceSystem.TEMPLATE_REGISTRY],
    CheckType.CALLING_HOURS: [SourceSystem.CONTACT_LOG, SourceSystem.D12],
    CheckType.CALLING_FREQUENCY: [SourceSystem.CONTACT_LOG, SourceSystem.D12],
    CheckType.VERIFICATION_BEFORE_DISCLOSURE: [SourceSystem.CONTACT_LOG, SourceSystem.RECORDING_STORE, SourceSystem.TRANSCRIPT_STORE],
    CheckType.NOTICE_TIMELINE: [SourceSystem.NOTICE_DISPATCH, SourceSystem.D12, SourceSystem.HOLIDAY_CALENDAR],
    CheckType.AGENT_CERTIFICATION: [SourceSystem.CONTACT_LOG, SourceSystem.CERT_REGISTER, SourceSystem.COLLECTOR_ROSTER],
    CheckType.RECORDING_COMPLETENESS: [SourceSystem.CONTACT_LOG, SourceSystem.RECORDING_STORE],
    CheckType.OTHER: [],
}


def read_request(path: str | Path, request_id: str) -> Request:
    """Read a PDF, email (.eml) or text file into a Request (text only; severity scale parsed later)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        return Request(request_id=request_id, source="pdf", path=str(path), text=text)
    if suffix == ".eml":
        from email import policy
        from email.parser import BytesParser

        msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        body = msg.get_body(preferencelist=("plain", "html"))
        text = f"Subject: {msg['subject'] or ''}\n\n" + (body.get_content() if body else "")
        return Request(request_id=request_id, source="email", path=str(path), text=text)
    return Request(request_id=request_id, source="text", path=str(path), text=path.read_text(encoding="utf-8"))


def extract_sample_accounts(text: str) -> list[str]:
    """Account references listed after a 'Sampled accounts:' heading, in order, without duplicates, exactly as written.
    They can be loan account numbers (what an auditor uses) or CN account ids; see agent.pipeline.resolve_references."""
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


_STANDARD: list[tuple[CheckType, str, str]] = [  # (type, question wording, default severity)
    (CheckType.CONSENT_BEFORE_CONTACT, "Show that the borrower had given consent before every WhatsApp or SMS message was sent.", "Critical"),
    (CheckType.CALLING_HOURS, "Confirm that every collection call was made within the permitted calling hours.", "Critical"),
    (CheckType.CALLING_FREQUENCY, "Confirm that no borrower was called more often than the permitted daily frequency.", "Critical"),
    (CheckType.VERIFICATION_BEFORE_DISCLOSURE, "Where dues were disclosed on a call, show the borrower's identity was verified before disclosure.", "Critical"),
    (CheckType.NOTICE_TIMELINE, "Show that notices were served within the permitted timeline.", "Major"),
    (CheckType.AGENT_CERTIFICATION, "Confirm the recovery agent was certified on the date of each call they made.", "Major"),
    (CheckType.RECORDING_COMPLETENESS, "Provide the recording for every connected call.", "Minor"),
]
DEFAULT_SCALE = ["Critical", "Major", "Minor"]  # used when the request gives none (docs/decisions.md D-014)
_FULL_AUDIT = ("compliance audit", "guardrail", "all checks", "all the checks", "full audit", "everything", "all rules", "all the rules",
               "rules & data", "rules and data")
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]


def _month_start(d: date, offset: int = 0) -> date:
    i = d.year * 12 + d.month - 1 + offset
    return date(i // 12, i % 12 + 1, 1)


def parse_sample(text: str, today: date | None = None) -> dict:
    """What the request says about the sample: explicit accounts, a size, and a period to look at.

    The period is in India calendar days, start inclusive and end exclusive (docs/decisions.md D-009, D-014).
    Understands 'previous/last month', 'this month', 'last N days', 'last N months', 'March 2026' and
    'January to October 2026'. Returns {accounts, size, period}; period is None when none is stated."""
    today = today or date.today()
    t = text.lower()
    size = None
    m = re.search(r"sample(?:\s+size)?\s*(?:of|:|=|is)?\s*(\d[\d,]*)", t) or re.search(r"(\d[\d,]*)\s+(?:sampled\s+)?accounts", t)
    if m:
        size = int(m.group(1).replace(",", ""))
    period = None
    months = "|".join(_MONTHS)

    def make(start: date, end: date, label: str) -> dict:
        return {"start": start.isoformat(), "end": end.isoformat(), "label": label}

    if re.search(r"\b(previous|last|prior|preceding)\s+month\b", t):
        s = _month_start(today, -1)
        period = make(s, _month_start(today), f"{s:%B %Y} (previous month)")
    elif re.search(r"\b(this|current)\s+month\b", t):
        s = _month_start(today)
        period = make(s, _month_start(today, 1), f"{s:%B %Y} (this month)")
    elif m := re.search(r"\blast\s+(\d+)\s+days?\b", t):
        n = int(m.group(1))
        period = make(today - timedelta(days=n), today, f"the last {n} days")
    elif m := re.search(r"\blast\s+(\d+)\s+months?\b", t):
        n = int(m.group(1))
        period = make(_month_start(today, -n), _month_start(today), f"the last {n} months")
    elif m := re.search(rf"\b({months})\s+to\s+({months})\s+(\d{{4}})\b", t):
        a, b, y = _MONTHS.index(m.group(1)) + 1, _MONTHS.index(m.group(2)) + 1, int(m.group(3))
        period = make(date(y, a, 1), _month_start(date(y, b, 1), 1), f"{m.group(1).title()} to {m.group(2).title()} {y}")
    elif m := re.search(rf"\b({months})\s+(\d{{4}})\b", t):
        s = date(int(m.group(2)), _MONTHS.index(m.group(1)) + 1, 1)
        period = make(s, _month_start(s, 1), f"{s:%B %Y}")
    return {"accounts": extract_sample_accounts(text), "size": size, "period": period}


def _parse_instruction(request: Request) -> tuple[list[CheckSpec], list[str]]:
    """The request is an instruction, not numbered questions: test the guardrails it asks about, or all of
    them for a general compliance audit. The auditor confirms the result before anything runs."""
    t = request.text.lower()
    asked = {ct for ct, words in _KEYWORDS if any(w in t for w in words)}
    if any(w in t for w in _FULL_AUDIT) or not asked:
        asked = {ct for ct, _, _ in _STANDARD}
    checks = []
    for i, (ct, question, severity) in enumerate((s for s in _STANDARD if s[0] in asked), 1):
        checks.append(CheckSpec(check_id=f"Q{i}", question_ref=f"Q{i}", question_text=question, check_type=ct,
                                sample={"source": "request_text"}, test={"severity": severity}, sources=_SOURCES[ct]))
    return checks, list(DEFAULT_SCALE)


def _parse_fallback(request: Request) -> tuple[list[CheckSpec], list[str]]:
    if not _QUESTION.search(request.text):
        return _parse_instruction(request)
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
If the request is an instruction rather than numbered questions (for example "run a compliance audit of all the guardrails"),
make one check per guardrail it asks about (all seven check types for a full compliance audit), numbered Q1, Q2, ...
and use the severity scale Critical, Major, Minor if the request gives none. Ignore the period and the sample size:
they are read separately.

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
