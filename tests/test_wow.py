"""Triage, the letter claims check, the second reading, and that the letter the platform writes passes its own claims check."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent.core import llm
from agent.core.contracts import CheckSpec, CheckType
from agent.intake.triage import ACCOUNT_CHECK, NOT_TESTABLE, VENDOR_DOCUMENT, classify, triage_checks
from agent.runtime import skeptic
from agent.services import letter_lint, pack

# ---------------------------------------------------------------- triage


@pytest.mark.parametrize("question,kind", [
    ("Provide the signed agreement and the GST certificate of the agency", VENDOR_DOCUMENT),
    ("Share the fidelity insurance policy and the business continuity plan", VENDOR_DOCUMENT),
    ("Confirm that collectors follow the dress code on visits", NOT_TESTABLE),
    ("Were any gifts offered to bank staff?", NOT_TESTABLE),
    ("Describe the weather on the day", NOT_TESTABLE),
])
def test_unmapped_questions_are_sorted(question, kind):
    got = classify(question, CheckType.OTHER)
    assert got["kind"] == kind and got["reason"]


def test_a_question_with_a_test_is_an_account_check():
    assert classify("Calls only between 8 and 7", CheckType.CALLING_HOURS)["kind"] == ACCOUNT_CHECK


def test_triage_is_recorded_on_the_check():
    c = CheckSpec(check_id="Q2", question_ref="Q2", question_text="Provide the CCTV retention policy", check_type=CheckType.OTHER, sample={}, test={}, sources=[])
    assert triage_checks([c])[0].test["triage"]["kind"] == VENDOR_DOCUMENT


# ---------------------------------------------------------------- a fake audit to write and check a letter against


def _audit():
    cite = {"source_system": "D4", "source_table": "t", "record_key": "k", "record_ts_utc": datetime(2026, 3, 1, tzinfo=UTC), "extract": {}, "role": "primary"}
    checks = [{"check_id": "Q1", "question_ref": "Q1", "question_text": "Consent before messages", "check_type": "consent_before_contact", "test_definition": {}},
              {"check_id": "Q2", "question_ref": "Q2", "question_text": "Provide the signed agreement", "check_type": "other", "test_definition": {"triage": {"kind": "vendor_document", "reason": "x"}}},
              {"check_id": "Q3", "question_ref": "Q3", "question_text": "Dress code", "check_type": "other", "test_definition": {"triage": {"kind": "not_testable", "reason": "No system of record shows this."}}}]
    base = {"disposition": None, "review_comment": None, "reviewer": None, "evidence_query": None}
    findings = [{"finding_id": 101, "check_id": "Q1", "account_id": "A1", "subject_ref": "m1", "status": "gap", "severity": "Critical", "reason": "Message m1 sent without consent.", **base},
                {"finding_id": 102, "check_id": "Q1", "account_id": "A2", "subject_ref": None, "status": "evidenced", "severity": None, "reason": "All 2 tested events passed.", **base},
                {"finding_id": 103, "check_id": "Q1", "account_id": "A3", "subject_ref": "m3", "status": "cannot_determine", "severity": None, "reason": "Tie at the same second.", **base}]
    return {"run": {"request_id": "R-1", "lender": "Bank", "severity_scale": ["Critical", "Major"]}, "checks": checks, "findings": findings,
            "cites": {101: [cite], 102: [cite]}, "sample_n": {"Q1": 3, "Q2": 3, "Q3": 3}, "responses": {}, "letter": None, "reviews": []}


@pytest.fixture()
def audit(monkeypatch):
    d = _audit()
    monkeypatch.setattr(pack, "collect", lambda run_id: d)
    monkeypatch.setattr(letter_lint, "collect", lambda run_id: d)
    return d


def test_the_letter_the_platform_writes_passes_its_own_check(audit):
    body = pack.generate_letter(uuid4())
    assert letter_lint.lint(uuid4(), body) == []
    assert "3a. Documents to be provided by the agency" in body and "Provide the signed agreement" in body
    assert "cannot determine" in body and "Dress code" in body


def test_vendor_documents_and_untestable_items_are_never_claimed(audit):
    body = pack.generate_letter(uuid4())
    q2 = body.split("### Q2.")[1].split("###")[0]
    assert "not** evidenced" in q2 and "evidenced as compliant" not in q2


def _edited(audit, old, new):
    body = pack.generate_letter(uuid4())
    assert old in body, old
    return letter_lint.lint(uuid4(), body.replace(old, new, 1))


def test_a_changed_headline_number_is_caught(audit):
    problems = _edited(audit, "We found **1 gap(s)", "We found **9 gap(s)")
    assert any("1 gap(s)" in p["problem"] for p in problems)


def test_a_changed_result_sentence_is_caught(audit):
    problems = _edited(audit, "1 were evidenced as compliant", "3 were evidenced as compliant")
    assert problems and "tested" in problems[0]["problem"]


def test_a_statement_without_a_reference_is_caught(audit):
    body = pack.generate_letter(uuid4()).replace("## 4.", "All accounts were found compliant.\n\n## 4.", 1)
    assert any("no finding or check" in p["problem"] for p in letter_lint.lint(uuid4(), body))


def test_a_reference_to_a_finding_that_does_not_exist_is_caught(audit):
    problems = _edited(audit, "[F101]", "[F999]")
    assert any("not a finding" in p["problem"] for p in problems)


def test_a_finding_reference_must_match_the_account_named(audit):
    problems = _edited(audit, "- A1 (m1)", "- A2 (m1)")
    assert any("belongs to account A1" in p["problem"] for p in problems)


def test_management_comments_are_their_own_words(audit):
    d = audit
    d["responses"] = {"Q1": {"body": "We resolved 12 of these in October and 100% are now compliant."}}
    body = pack.generate_letter(uuid4())
    assert "100% are now compliant" in body and letter_lint.lint(uuid4(), body) == []


# ---------------------------------------------------------------- the second reading


def test_only_masked_numbers_and_no_names_reach_the_model():
    got = skeptic._safe({"contact_no": "9876543210", "customer_name": "A Person", "channel": "SMS", "phone": "1234567890"})
    assert got == {"contact_no": "XXXXXX3210", "channel": "SMS", "phone": "XXXXXX7890"}


def _item():
    return {"finding_id": 7, "rule": "r", "reason": "Message sent without consent.", "citations": [{"source_table": "t", "record_key": "k", "record_ts_utc": None, "role": "primary", "extract": {}}]}


@pytest.mark.parametrize("answer,verdict", [
    ({"verdict": "supports", "concern": "ok"}, "supports"),
    ({"verdict": "disputes", "concern": "The consent row is dated before the message."}, "disputes"),
    ({"verdict": "disputes", "concern": ""}, "unclear"),   # a dispute must say why
    ({"verdict": "maybe", "concern": "hm"}, "unclear"),
    ("not json at all", "unclear"),
])
def test_the_second_reading_gives_one_of_three_answers(monkeypatch, answer, verdict):
    monkeypatch.setattr(llm, "reason_json", lambda *a, **k: answer)
    assert skeptic.challenge_one(_item())["verdict"] == verdict


def test_the_second_reading_is_skipped_without_a_model(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    assert skeptic.challenge_many([_item()]) == ([], 1)


def test_the_second_reading_never_touches_findings():
    """It can only add rows to finding_challenges; the service holds no statement that updates or deletes a finding."""
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "agent" / "services" / "challenge.py").read_text(encoding="utf-8")
    assert "UPDATE audit.findings" not in text and "DELETE" not in text.upper().replace("DELETED", "") and "INSERT INTO audit.finding_challenges" in text
