from pathlib import Path

from agent.contracts import CheckType, Request
from agent.parser.request_parser import _parse_fallback, extract_sample_accounts

TEXT = """Q1. Show consent before every WhatsApp message.
Q2. Confirm calls were within permitted hours and within the permitted frequency.
Q3. Describe your weather policy.

Severity scale for gaps:
  Critical - breach affecting the borrower (Q1, Q2)
  Minor    - evidence completeness (Q3)

Sampled accounts:
ACC00001, ACC00002,
ACC00003
"""


def _request() -> Request:
    return Request(request_id="T", source="text", text=TEXT)


def test_compound_question_splits_and_unknown_is_kept():
    checks, scale = _parse_fallback(_request())
    assert [c.check_id for c in checks] == ["Q1", "Q2a", "Q2b", "Q3"]
    assert {c.check_type for c in checks if c.question_ref == "Q2"} == {CheckType.CALLING_HOURS, CheckType.CALLING_FREQUENCY}
    assert checks[-1].check_type is CheckType.OTHER  # never dropped
    assert scale == ["Critical", "Minor"]
    assert checks[0].test["severity"] == "Critical"


def test_sample_accounts_extracted_in_order():
    assert extract_sample_accounts(TEXT) == ["ACC00001", "ACC00002", "ACC00003"]


def test_synthetic_request_parses_to_seven_checks():
    text = (Path(__file__).resolve().parents[1] / "eval" / "requests" / "SYN-01.txt")
    if text.exists():
        checks, _ = _parse_fallback(Request(request_id="T", source="text", text=text.read_text(encoding="utf-8")))
        assert len(checks) == 7
