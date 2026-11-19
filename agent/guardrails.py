"""Knowledge base and guardrails.

A circular, policy or SOP is split into numbered clauses. Each independently testable obligation becomes a guardrail
(one per clause per control), linked to the clause, with a default severity and a priority weight (1 to 3). Guardrails
are versioned (audit.guardrail): a run records the version it applied. The weight only orders the review queue; it never
changes whether the evidence shows a gap.

Suggesting guardrails from a clause is keyword-based here (no model call): it proposes, Compliance reviews and publishes.
"""
from __future__ import annotations

import re
from datetime import date

from agent.db import read_rows

SEVERITY_DEFAULT = {"consent_before_contact": "Critical", "calling_hours": "Critical", "calling_frequency": "Critical",
                    "verification_before_disclosure": "Critical", "notice_timeline": "Major", "agent_certification": "Major",
                    "recording_completeness": "Minor"}

TITLES = {"consent_before_contact": "Consent before contact", "calling_hours": "Calls within permitted hours",
          "calling_frequency": "Call attempts within the daily cap", "verification_before_disclosure": "Identity verified before dues disclosed",
          "notice_timeline": "Notices dispatched and served on time", "agent_certification": "Recovery agent certified",
          "recording_completeness": "Recording retained for every connected call"}

_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("consent_before_contact", (r"\bconsent\b", r"opt[- ]?in", r"\bpermission\b", r"whatsapp", r"\bsms\b")),
    ("calling_hours", (r"calling hours", r"between\s+\d{1,2}", r"\d\s*(?:a\.?m|p\.?m)", r"time of (?:the )?day", r"\bhours\b")),
    ("calling_frequency", (r"per day", r"times (?:a|per|in a) day", r"\battempts?\b", r"frequency", r"number of calls")),
    ("verification_before_disclosure", (r"identity", r"\bverif", r"authenticat", r"before disclos")),
    ("notice_timeline", (r"\bnotices?\b", r"within\s+\w+\s+(?:working |business |calendar )?days")),
    ("agent_certification", (r"certif", r"\bDRA\b", r"authori[sz]ed (?:agent|recovery)", r"trained and")),
    ("recording_completeness", (r"\brecord(?:ing|ed)?\b", r"retain", r"retention")),
]
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*[.)]?|\([a-zA-Z0-9]{1,4}\)|[A-Z][.)])\s+(\S.*)$")


def split_clauses(text: str) -> list[tuple[str, str]]:
    """(clause number, text) pairs. Numbered lines each start a clause; an unnumbered paragraph is one clause (¶1, ¶2, ...)."""
    out: list[tuple[str, str]] = []
    for i, para in enumerate(re.split(r"\n\s*\n", text.strip()), 1):
        lines = [ln for ln in para.splitlines() if ln.strip()]
        if not lines:
            continue
        if any(_NUMBERED.match(ln) for ln in lines):
            for ln in lines:
                m = _NUMBERED.match(ln)
                if m:
                    out.append((m.group(1).rstrip(".)"), m.group(2).strip()))
                elif out:  # continuation of the previous clause
                    out[-1] = (out[-1][0], out[-1][1] + " " + ln.strip())
                else:
                    out.append((f"¶{i}", ln.strip()))
        else:
            out.append((f"¶{i}", " ".join(ln.strip() for ln in lines)))
    return out


def _n(x: str) -> int:
    return int(x) if x.isdigit() else _WORDS[x.lower()]


def _hhmm(h: str, m: str | None, ap: str | None) -> str:
    hour = int(h) % 12 + (12 if ap and ap.lower().startswith("p") else 0) if ap else int(h)
    return f"{hour:02d}:{int(m or 0):02d}"


def extract_parameters(check_type: str, text: str) -> dict:
    """The limits a clause states, for reference. The tests themselves read the D12 rule rows, so a published guardrail
    whose numbers differ from D12 is a discrepancy for Compliance to resolve, not something the platform silently picks."""
    t = text.lower()
    if check_type == "calling_hours":
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s*(?:to|and|-|–)\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", t)
        if m:
            return {"window_start": _hhmm(m.group(1), m.group(2), m.group(3) or m.group(6)), "window_end": _hhmm(m.group(4), m.group(5), m.group(6))}
    if check_type == "calling_frequency":
        m = re.search(_NUM + r"\s+(?:calls?|attempts?|times?)\s+(?:per|a|in a|each)\s+(?:calendar\s+)?day", t)
        if m:
            return {"max_per_day": _n(m.group(1)), "counting_unit": "contact number" if "number" in t else "borrower"}
    if check_type == "notice_timeline":
        m = re.search(r"within\s+" + _NUM + r"\s+(working|business|calendar)?\s*days", t)
        if m:
            return {"days": _n(m.group(1)), "day_type": m.group(2) or "calendar"}
    if check_type == "consent_before_contact":
        return {"channels": [c.upper() for c in ("whatsapp", "sms", "email") if c in t] or ["WHATSAPP", "SMS"], "prior_consent_required": True}
    if check_type == "recording_completeness":
        m = re.search(_NUM + r"\s+(months?|years?)", t)
        if m:
            return {"retention": f"{_n(m.group(1))} {m.group(2)}"}
    return {}


def suggest(clauses: list[tuple[str, str]]) -> list[dict]:
    """Draft guardrails: one per clause per control the clause appears to state. Nothing is published."""
    drafts = []
    for no, body in clauses:
        for check_type, patterns in _TOPICS:
            if any(re.search(p, body, re.IGNORECASE) for p in patterns):
                drafts.append({"check_type": check_type, "title": TITLES[check_type], "obligation": body[:600], "source_clause": no,
                               "parameters": extract_parameters(check_type, body), "default_severity": SEVERITY_DEFAULT[check_type]})
    return drafts


def published_for(check_type: str, on: date | None = None) -> dict | None:
    """The guardrail a run applies for a control: the published version with the latest effective date on or before `on`."""
    rows = read_rows("""SELECT guardrail_id, version, title, default_severity, priority_weight, effective_from
                        FROM audit.guardrail WHERE check_type = %s AND status = 'published' AND effective_from <= %s
                        ORDER BY effective_from DESC, version DESC, guardrail_id LIMIT 1""", (check_type, on or date.today()))
    return rows[0] if rows else None
