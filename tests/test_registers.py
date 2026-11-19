"""Issues, the audit plan and the risk matrix: the rules that keep them honest."""
import os
from datetime import date

import pytest

from agent.services import issues, plan, risk

needs_db = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")


# ---------------------------------------------------------------- risk (no database)


def test_bands_and_rating_follow_the_matrix():
    assert risk.band(0.52, risk.LIKELIHOOD_BANDS)[0] == "High" and risk.band(0.10, risk.LIKELIHOOD_BANDS)[0] == "Medium" and risk.band(0.0, risk.LIKELIHOOD_BANDS)[0] == "Low"
    assert risk.rating(3, 3) == "High" and risk.rating(2, 3) == "High" and risk.rating(1, 3) == "Medium" and risk.rating(2, 1) == "Low" and risk.rating(1, 1) == "Low"


def test_impact_comes_from_the_place_on_the_requests_scale():
    assert [risk.severity_weight(r) for r in (1, 2, 3, 4, None)] == [5, 3, 1, 1, 1]


# ---------------------------------------------------------------- plan (no database)


def test_recurring_entries_move_by_whole_months_and_never_overflow():
    assert plan._add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert plan._add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
    assert plan._add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)


def test_plan_entries_are_validated():
    for kwargs, why in [({"title": " "}, "title"), ({"kind": "other"}, "kind"), ({"recurrence": "weekly"}, "recurrence"),
                        ({"planned_start": date(2026, 5, 2), "due": date(2026, 5, 1)}, "due")]:
        args = {"title": "x", "lender": None, "scope": None, "kind": "audit", "planned_start": None, "due": None, "owner": None, "recurrence": "none", "actor": "t", **kwargs}
        with pytest.raises(ValueError):
            plan.create(**args)


# ---------------------------------------------------------------- issues (database)


@pytest.fixture()
def gaps():
    from agent.core.db import connect
    with connect() as conn:
        rows = conn.execute("""SELECT f.finding_id FROM audit.findings f JOIN audit.runs r USING (run_id) WHERE f.status = 'gap' AND r.kind = 'audit' AND r.status = 'completed'
                               AND NOT EXISTS (SELECT 1 FROM audit.issue_findings l WHERE l.finding_id = f.finding_id) ORDER BY f.finding_id DESC LIMIT 3""").fetchall()
        cannot = conn.execute("SELECT finding_id FROM audit.findings WHERE status = 'cannot_determine' LIMIT 1").fetchone()
    if len(rows) < 3 or not cannot:
        pytest.skip("not enough findings to test against")
    made: list[int] = []
    yield [r["finding_id"] for r in rows], cannot["finding_id"], made
    with connect() as conn:  # the test's own rows are removed; findings are never touched
        for i in made:
            conn.execute("DELETE FROM audit.issue_events WHERE issue_id = %s", (i,))
            conn.execute("DELETE FROM audit.issue_findings WHERE issue_id = %s", (i,))
            conn.execute("DELETE FROM audit.issues WHERE issue_id = %s", (i,))


@needs_db
def test_an_issue_lifecycle_and_its_rules(gaps):
    ids, cannot, made = gaps
    with pytest.raises(ValueError, match="Only reported gaps"):
        issues.create([cannot], "x", None, None, None, "Asha")
    with pytest.raises(ValueError, match="title"):
        issues.create(ids[:1], " ", None, None, None, "Asha")
    i = issues.create(ids[:2], "Consent gaps at Northstar", "Ravi", date(2027, 1, 31), None, "Asha")
    made.append(i)
    with pytest.raises(ValueError, match="already in open issue"):  # nothing is tracked twice
        issues.create(ids[1:2], "again", None, None, None, "Asha")
    with pytest.raises(ValueError, match="cannot go straight"):
        issues.update(i, "Ravi", status="verified")
    with pytest.raises(ValueError, match="Say how"):  # resolving needs the story
        issues.update(i, "Ravi", status="resolved")
    issues.update(i, "Ravi", status="resolved", note="Switched off the out-of-hours campaign on 3 Dec; screenshot in the pack.")
    with pytest.raises(ValueError, match="different person"):  # the person who fixed it cannot verify it
        issues.update(i, "ravi", status="verified")
    issues.update(i, "Asha", status="verified")
    with pytest.raises(ValueError):
        issues.update(i, "Asha", status="open")  # closed stays closed
    from agent.core.db import connect
    with connect() as conn:
        kinds = [r["kind"] for r in conn.execute("SELECT kind FROM audit.issue_events WHERE issue_id = %s ORDER BY event_id", (i,))]
        status = conn.execute("SELECT status FROM audit.findings WHERE finding_id = %s", (ids[0],)).fetchone()["status"]
    assert kinds == ["created", "status", "note", "status"] and status == "gap", "every change is an event, and the finding itself is untouched"
    j = issues.create(ids[1:2], "A new issue once the first is closed", None, None, None, "Asha")  # a closed issue frees its gaps
    made.append(j)


@needs_db
def test_the_registers_answer(gaps):
    from fastapi.testclient import TestClient

    from agent.web.app import app
    c = TestClient(app)
    assert {"total", "rows", "check_types", "runs"} <= set(c.get("/api/exceptions", params={"limit": 2}).json())
    assert c.get("/api/exceptions.csv").text.startswith("audit,finding_id")
    assert c.get("/api/issues").status_code == 200 and c.get("/api/plan").status_code == 200 and c.get("/api/issues/999999").status_code == 404
    assert c.post("/api/issues", json={"finding_ids": [1], "title": "x", "actor": ""}).status_code == 400
    assert c.post("/api/plan", json={"title": "x", "actor": ""}).status_code == 400
