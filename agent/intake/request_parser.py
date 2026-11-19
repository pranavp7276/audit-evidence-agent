"""Turn an audit request (PDF or email text) into a list of CheckSpecs.

This is the main LLM step. Output must validate against agent.core.contracts.CheckSpec; anything
that does not validate is rejected, not patched. Compound questions become several checks
sharing a question_ref (Q3 -> Q3a, Q3b). A question that maps to no known check type becomes
check_type=OTHER so it still appears in the response as unanswered, never silently dropped.

With SARVAM_API_KEY set, each numbered question goes to the decision model (sarvam-prism) to pick its check with a confidence,
and bundled or unclear questions and plain instructions go to the reasoning model (DeepSeek). Without a key, or if the service fails,
a keyword fallback is used (docs/decisions.md D-012, D-020); it only knows the seven check types and the "Q<n>." layout.
The auditor confirms the result before anything runs.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from agent.core import llm
from agent.core.contracts import CheckSpec, CheckType, Request, SourceSystem
from agent.intake.triage import triage_checks

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
    (CheckType.TEMPLATE_APPROVAL, ("template",)),
    (CheckType.COLLECTOR_ACTIVE, ("active collector", "terminated", "collector was active")),
    (CheckType.CALLER_ID_REGISTERED, ("registered to the agency", "personal mobile", "caller id", "registered number")),
    (CheckType.THIRD_PARTY_DISCLOSURE, ("reference contact", "third party", "third-party", "did not provide")),
]
_SOURCES: dict[CheckType, list[SourceSystem]] = {
    CheckType.CONSENT_BEFORE_CONTACT: [SourceSystem.CONTACT_LOG, SourceSystem.CONSENT_REGISTRY, SourceSystem.TEMPLATE_REGISTRY],
    CheckType.CALLING_HOURS: [SourceSystem.CONTACT_LOG, SourceSystem.D12],
    CheckType.CALLING_FREQUENCY: [SourceSystem.CONTACT_LOG, SourceSystem.D12],
    CheckType.VERIFICATION_BEFORE_DISCLOSURE: [SourceSystem.CONTACT_LOG, SourceSystem.RECORDING_STORE, SourceSystem.TRANSCRIPT_STORE],
    CheckType.NOTICE_TIMELINE: [SourceSystem.NOTICE_DISPATCH, SourceSystem.D12, SourceSystem.HOLIDAY_CALENDAR],
    CheckType.AGENT_CERTIFICATION: [SourceSystem.CONTACT_LOG, SourceSystem.CERT_REGISTER, SourceSystem.COLLECTOR_ROSTER],
    CheckType.RECORDING_COMPLETENESS: [SourceSystem.CONTACT_LOG, SourceSystem.RECORDING_STORE],
    CheckType.TEMPLATE_APPROVAL: [SourceSystem.CONTACT_LOG, SourceSystem.TEMPLATE_REGISTRY],
    CheckType.COLLECTOR_ACTIVE: [SourceSystem.CONTACT_LOG, SourceSystem.COLLECTOR_ROSTER],
    CheckType.CALLER_ID_REGISTERED: [SourceSystem.CONTACT_LOG, SourceSystem.CALLER_ID_REGISTRY],
    CheckType.THIRD_PARTY_DISCLOSURE: [SourceSystem.CONTACT_LOG, SourceSystem.RECORDING_STORE, SourceSystem.TRANSCRIPT_STORE],
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
    They can be loan account numbers (what an auditor uses) or CN account ids; see agent.intake.sampling.resolve_references."""
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
    (CheckType.TEMPLATE_APPROVAL, "Show that every WhatsApp or SMS message was sent on a template approved at the time it was sent.", "Major"),
    (CheckType.COLLECTOR_ACTIVE, "Confirm that the collector who made each call was an active collector on the date of the call.", "Major"),
    (CheckType.CALLER_ID_REGISTERED, "Confirm that every call was placed from a number registered to the agency, not from a personal mobile.", "Major"),
    (CheckType.THIRD_PARTY_DISCLOSURE, "Confirm that no dues were disclosed on calls to reference contacts the borrower did not provide.", "Critical"),
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
    elif m := re.search(rf"\b({months})\s+(\d{{4}})\s+(?:to|through|until|-)\s+({months})\s+(\d{{4}})\b", t):
        a, y1, b, y2 = _MONTHS.index(m.group(1)) + 1, int(m.group(2)), _MONTHS.index(m.group(3)) + 1, int(m.group(4))
        period = make(date(y1, a, 1), _month_start(date(y2, b, 1), 1), f"{m.group(1).title()} {y1} to {m.group(3).title()} {y2}")
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


_CONTROLS = {
    "consent_before_contact": "Borrower consent before WhatsApp or SMS messages are sent",
    "calling_hours": "Calls placed only within the permitted calling hours",
    "calling_frequency": "Number of call attempts to a borrower or contact number within the permitted daily or periodic limit",
    "verification_before_disclosure": "Borrower identity verified before dues or loan details are disclosed on a call",
    "notice_timeline": "Legal or demand notices dispatched and served within the required timeline",
    "agent_certification": "Recovery agents or collectors certified, authorised or trained on the date of the call",
    "recording_completeness": "Call recordings available and retained for calls",
    "template_approval": "Messages sent only on templates approved at the time they were sent",
    "collector_active": "The collector who made a call was an active (not terminated or inactive) collector on the call date",
    "caller_id_registered": "Calls placed only from numbers registered to the agency, never from a personal mobile",
    "third_party_disclosure": "No dues disclosed on calls to reference contacts the borrower did not provide",
    "other": "None of the above: the question tests something else",
}
LOW_CONFIDENCE = 0.7


def _decide_type(text: str) -> tuple[CheckType, float, bool]:
    """The decision model's choice of check for one question, its confidence, and whether the question seems to bundle several tests."""
    answers = llm.decide(llm.strip_sample(text), {
        "check_type": {"type": "choice", "instructions": "Which control does this audit question test?", "criteria": _CONTROLS},
        "bundles": {"type": "noul", "instructions": "Does the question ask for more than one separate test (for example hours and frequency, or calls and certification)?"}})
    pick = answers["check_type"]
    return CheckType(pick["choice"]), float(pick.get("confidence", 0)), float(answers["bundles"].get("noul", 0)) > 0.5


def _split_types(question: str) -> list[CheckType]:
    """The reasoning model lists the separate controls a bundled question asks about."""
    data = llm.reason_json(
        "An auditor's question may ask for several separate tests. List every control it asks about, using only these ids: "
        + ", ".join(k for k in _CONTROLS if k != "other") + '. Reply ONLY with JSON like {"controls": ["calling_hours", "calling_frequency"]}. '
        "Include a control only if the question actually asks for it.\n\nQuestion: " + llm.strip_sample(question), max_tokens=400)
    out = [CheckType(c) for c in data.get("controls", []) if c in _CONTROLS and c != "other"]
    return out or [CheckType.OTHER]


def _parse_questions_with_models(request: Request) -> tuple[list[CheckSpec], list[str]]:
    scale, by_q = _severity_by_question(request.text)
    checks: list[CheckSpec] = []
    for ref, question in _QUESTION.findall(request.text):
        ctype, conf, bundled = _decide_type(question)
        if ctype is CheckType.OTHER and conf >= LOW_CONFIDENCE:
            types, reader = [CheckType.OTHER], f"{llm.models()['decision']} ({conf:.0%} sure)"
        elif bundled or conf < LOW_CONFIDENCE:
            types, reader = _split_types(question), f"{llm.models()['reasoning']} (question looked bundled or unclear)"
        else:
            types, reader = [ctype], f"{llm.models()['decision']} ({conf:.0%} sure)"
        for i, t in enumerate(types):
            test = {"severity": by_q[ref]} if by_q.get(ref) else {}
            test.update(reader=reader, confidence=round(conf, 3))
            checks.append(CheckSpec(check_id=ref if len(types) == 1 else f"{ref}{chr(97 + i)}", question_ref=ref, question_text=question,
                                    check_type=t, sample={"source": "request_text"}, test=test, sources=_SOURCES[t]))
    return checks, scale


def _parse_instruction_with_models(request: Request) -> tuple[list[CheckSpec], list[str]]:
    data = llm.reason_json(
        "You read an instruction for a collections compliance audit and decide which controls to test. Use only these control ids: "
        + ", ".join(f"{k} ({v})" for k, v in _CONTROLS.items() if k != "other")
        + '. If it asks for a full compliance audit or all guardrails, include every control. Otherwise include only those it names or clearly implies. '
        'Reply ONLY with JSON like {"controls": ["calling_hours"]}.\n\nInstruction: ' + llm.strip_sample(request.text), max_tokens=500)
    wanted = {c for c in data.get("controls", []) if c in _CONTROLS and c != "other"}
    if not wanted:
        raise llm.LLMError("The model chose no controls.")
    reader = f"{llm.models()['reasoning']}"
    checks = []
    for i, (ct, question, severity) in enumerate((s for s in _STANDARD if s[0].value in wanted), 1):
        checks.append(CheckSpec(check_id=f"Q{i}", question_ref=f"Q{i}", question_text=question, check_type=ct, sample={"source": "request_text"},
                                test={"severity": severity, "reader": reader}, sources=_SOURCES[ct]))
    return checks, list(DEFAULT_SCALE)


def parse_checks_with_info(request: Request) -> tuple[list[CheckSpec], list[str], dict]:
    """Return (checks, severity_scale, info). With model access the questions are read by the decision and reasoning
    models; if the service fails, or there is no key, the keyword reader is used and info says so. The auditor confirms
    the result before anything runs (docs/decisions.md D-020)."""
    info = {"reader": "keyword", "models": None, "note": None}
    if llm.available():
        try:
            checks, scale = (_parse_questions_with_models(request) if _QUESTION.search(request.text) else _parse_instruction_with_models(request))
            if checks:
                return triage_checks(checks), scale, {"reader": "models", "models": llm.models(), "note": None}
        except (llm.LLMError, ValueError, KeyError, TypeError) as exc:
            info["note"] = f"The model service could not read this request ({exc}). The keyword reader was used instead; please check every row."
    checks, scale = _parse_fallback(request)
    return triage_checks(checks), scale, info


def parse_checks(request: Request) -> tuple[list[CheckSpec], list[str]]:
    """Return (checks, severity_scale)."""
    checks, scale, _ = parse_checks_with_info(request)
    return checks, scale
