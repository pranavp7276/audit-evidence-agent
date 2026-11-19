"""Triage: before anything is tested, say what kind of question each one is.

  account_check    a test exists: it is run per sampled account against the data
  vendor_document  an agency artefact (a contract, a licence, an insurance policy, CCTV, a continuity plan): none of our systems hold it,
                   so it is never evidenced from our data; the agency must supply it
  not_testable     no system of record exists for it (dress code, where a visit took place, a gift): always cannot determine,
                   said plainly in the response

Only a question that maps to no check is looked at here; a question a check covers is an account check. The reading is by wording and is
shown to the auditor to confirm. The reason always says which words decided it, so the auditor can disagree.
"""
from __future__ import annotations

import re

from agent.core.contracts import CheckSpec, CheckType

ACCOUNT_CHECK, VENDOR_DOCUMENT, NOT_TESTABLE = "account_check", "vendor_document", "not_testable"
KINDS = {ACCOUNT_CHECK: "Tested per account", VENDOR_DOCUMENT: "Agency to provide a document", NOT_TESTABLE: "Not testable from our systems"}

# Agency-level artefacts an audit asks the agency to produce (contracts, licences, insurance, IT and premises controls, staff files).
_VENDOR = ("contract", "agreement", "statement of work", "sow", "licence", "license", "registration", "certificate of incorporation", "gst", "pan card",
           "insurance", "fidelity", "cctv", "business continuity", "bcp", "disaster recovery", "usb", "firewall", "antivirus", "access control", "biometric",
           "premises", "office space", "lease", "org chart", "organisation chart", "organization chart", "policy document", "audited financial", "balance sheet",
           "background verification", "police verification", "attrition", "sub-contract", "subcontract", "data retention policy", "it policy", "grievance policy")
# Conduct with no system of record: nothing in the call, message, notice or certification data can show it.
_NOT_TESTABLE = ("dress code", "attire", "uniform", "proximity", "visit location", "place of visit", "field visit", "house visit", "residence visit",
                 "gift", "gratuity", "bribe", "hospitality", "behaviour at", "behavior at", "body language", "id card worn", "photograph taken")


def _hits(text: str, words: tuple[str, ...]) -> list[str]:
    t = text.lower()
    return [w for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t)]


def classify(question: str, check_type: CheckType) -> dict:
    """What kind of question this is, and why. {"kind", "label", "reason"}."""
    if check_type is not CheckType.OTHER:
        return {"kind": ACCOUNT_CHECK, "label": KINDS[ACCOUNT_CHECK], "reason": "A test exists for this question and is run on every sampled account."}
    vendor, nope = _hits(question, _VENDOR), _hits(question, _NOT_TESTABLE)
    if vendor and len(vendor) >= len(nope):
        return {"kind": VENDOR_DOCUMENT, "label": KINDS[VENDOR_DOCUMENT],
                "reason": f"This asks for an agency artefact (matched: {', '.join(vendor[:3])}). None of our systems hold it, so it is listed for the agency to supply and never marked evidenced."}
    if nope:
        return {"kind": NOT_TESTABLE, "label": KINDS[NOT_TESTABLE],
                "reason": f"No system of record shows this (matched: {', '.join(nope[:3])}). It is reported as cannot determine and stated plainly in the response."}
    return {"kind": NOT_TESTABLE, "label": KINDS[NOT_TESTABLE],
            "reason": "No test exists for this question and no system of record is known for it. It is reported as unanswered and needs a manual response."}


def triage_checks(checks: list[CheckSpec]) -> list[CheckSpec]:
    """Record each check's kind on the check itself (test.triage), so the plan, the letter and the screens read the same thing."""
    for c in checks:
        c.test = {**c.test, "triage": classify(c.question_text, c.check_type)}
    return checks
