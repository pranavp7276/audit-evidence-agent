from pathlib import Path

from agent.core.contracts import CheckType, Request
from agent.intake.request_parser import _parse_fallback, extract_sample_accounts

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


def test_instruction_request_becomes_a_full_audit_with_period_and_size():
    from datetime import date

    from agent.intake.request_parser import DEFAULT_SCALE, _parse_fallback, parse_sample

    text = ("Run a compliance audit for all the accounts reached out within the previous month, all the necessary "
            "guardrails mentioned in the rules & data, are they being followed or not, and have put a sample size of 300")
    checks, scale = _parse_fallback(Request(request_id="T", source="text", text=text))
    assert [c.check_type for c in checks] == [t for t in CheckType if t is not CheckType.OTHER]  # every guardrail
    assert scale == DEFAULT_SCALE and checks[0].test["severity"] == "Critical" and checks[-1].test["severity"] == "Minor"
    s = parse_sample(text, today=date(2026, 11, 19))
    assert s["size"] == 300 and s["accounts"] == []
    assert (s["period"]["start"], s["period"]["end"]) == ("2026-10-01", "2026-11-01")  # end excluded


def test_instruction_naming_one_topic_tests_only_that():
    from agent.intake.request_parser import _parse_fallback

    checks, _ = _parse_fallback(Request(request_id="T", source="text", text="Check calling hours for last month, 50 accounts"))
    assert [c.check_type for c in checks] == [CheckType.CALLING_HOURS]


def test_periods_are_understood():
    from datetime import date

    from agent.intake.request_parser import parse_sample

    today = date(2026, 1, 15)  # the previous month crosses a year boundary
    assert parse_sample("accounts contacted last month", today)["period"]["start"] == "2025-12-01"
    last10 = parse_sample("the last 10 days", today)["period"]
    assert (last10["start"], last10["end"]) == ("2026-01-05", "2026-01-15")
    assert parse_sample("during March 2026", today)["period"]["end"] == "2026-04-01"
    assert parse_sample("covering January to October 2026", today)["period"]["end"] == "2026-11-01"
    assert parse_sample("no dates here", today)["period"] is None


def test_month_year_to_month_year_period():
    from datetime import date

    from agent.intake.request_parser import parse_sample

    p = parse_sample("covering November 2025 to October 2026", date(2026, 11, 19))["period"]
    assert (p["start"], p["end"]) == ("2025-11-01", "2026-11-01")
