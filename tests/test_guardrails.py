import os

import pytest
from fastapi.testclient import TestClient

from agent.knowledge.guardrails import extract_parameters, split_clauses, suggest
from agent.web.app import app

CIRCULAR = """1. Calling hours: collection calls may be made only between 8:00 a.m. and 7:00 p.m.

2. Not more than three attempts per day shall be made to the same contact number.

3. Notices shall be served within seven working days of the default trigger.

4. Agents must be certified; identity must be verified before dues are disclosed."""


def test_clauses_are_split_and_numbered():
    assert [n for n, _ in split_clauses(CIRCULAR)] == ["1", "2", "3", "4"]
    assert split_clauses("A paragraph with no number.\n\nAnother one.") == [("¶1", "A paragraph with no number."), ("¶2", "Another one.")]


def test_limits_are_read_from_a_clause():
    assert extract_parameters("calling_hours", "between 8:00 a.m. and 7:00 p.m.") == {"window_start": "08:00", "window_end": "19:00"}
    assert extract_parameters("calling_hours", "from 9 am to 6:30 pm") == {"window_start": "09:00", "window_end": "18:30"}
    assert extract_parameters("calling_frequency", "no more than five attempts a day to one number") == {"max_per_day": 5, "counting_unit": "contact number"}
    assert extract_parameters("notice_timeline", "served within 7 working days") == {"days": 7, "day_type": "working"}


def test_one_clause_can_state_two_controls_and_nothing_is_published():
    drafts = suggest(split_clauses(CIRCULAR))
    assert {(d["source_clause"], d["check_type"]) for d in drafts} >= {("1", "calling_hours"), ("2", "calling_frequency"), ("3", "notice_timeline"),
                                                                       ("4", "agent_certification"), ("4", "verification_before_disclosure")}
    assert all("status" not in d for d in drafts)  # drafts only; publishing is a separate, named act


client = TestClient(app)


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_guardrail_rules_are_enforced():
    base = {"check_type": "calling_hours", "title": "T", "obligation": "O", "default_severity": "Critical", "priority_weight": 1,
            "effective_from": "2026-01-01", "status": "draft", "created_by": "Tester"}

    def code(**over):
        return client.post("/api/guardrails", json={**base, **over}).status_code

    assert code(priority_weight=3) == 400                      # a weight above 1 needs a reason
    assert code(priority_weight=4, weight_reason="x") == 400   # only 1 to 3
    assert code(created_by="") == 400                          # unattributed
    assert code(check_type="nonsense") == 400
    assert code(status="live") == 400


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_seeded_guardrails_cover_every_check():
    rows = client.get("/api/guardrails").json()
    published = {g["check_type"] for g in rows if g["status"] == "published"}
    assert {"consent_before_contact", "calling_hours", "calling_frequency", "verification_before_disclosure", "notice_timeline",
            "agent_certification", "recording_completeness"} <= published
