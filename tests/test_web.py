import os

import pytest
from fastapi.testclient import TestClient

from agent.web.app import app

client = TestClient(app)


def test_front_end_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Audit Evidence Platform" in r.text
    assert client.get("/static/js/main.js").status_code == 200


def test_password_gate(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", auth=("anyone", "s3cret")).status_code == 200
    assert client.get("/api/config", auth=("anyone", "wrong")).status_code == 401


def test_new_run_needs_a_request():
    r = client.post("/api/runs", data={"request_id": "X", "text": "   "})
    assert r.status_code == 400


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_unknown_run_and_table():
    assert client.get("/api/runs/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/record", params={"table": "audit.findings", "key": "1"}).status_code == 400


def _completed_run():
    from agent.core.db import connect

    with connect() as conn:
        row = conn.execute("""SELECT r.run_id FROM audit.runs r WHERE r.status = 'completed' AND EXISTS (
                                  SELECT 1 FROM audit.findings f WHERE f.run_id = r.run_id AND f.status = 'gap')
                              ORDER BY r.started_at DESC LIMIT 1""").fetchone()
    return str(row["run_id"]) if row else None


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_review_rules_are_enforced():
    run = _completed_run()
    if not run:
        pytest.skip("no completed run to test against")
    ids = client.get(f"/api/runs/{run}/findings", params={"status": "gap", "limit": 1}).json()["rows"]
    if not ids:
        pytest.skip("run has no gaps")
    fid = ids[0]["finding_id"]
    url = f"/api/runs/{run}/reviews"
    def code(**body):
        return client.post(url, json=body).status_code

    assert code(finding_ids=[], disposition="confirmed", reviewer="T") == 400  # nothing selected
    assert code(finding_ids=[fid], disposition="confirmed", reviewer="") == 400  # unattributed
    assert code(finding_ids=[fid], disposition="disputed", reviewer="T") == 400  # a dispute needs a reason
    assert code(finding_ids=[fid], disposition="bogus", reviewer="T") == 400
    assert code(finding_ids=[999999999], disposition="confirmed", reviewer="T") == 400  # not in this run


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_letter_cannot_be_approved_with_placeholders():
    run = _completed_run()
    if not run:
        pytest.skip("no completed run to test against")
    r = client.post(f"/api/runs/{run}/letter", json={"body": "**Management comment:** [To be completed by management]",
                                                      "status": "approved", "author": "T"})
    assert r.status_code == 400 and "placeholders" in r.json()["detail"]


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_gaps_are_reported_not_hidden_by_a_dispute_view():
    run = _completed_run()
    if not run:
        pytest.skip("no completed run to test against")
    detail = client.get(f"/api/runs/{run}").json()
    gaps = client.get(f"/api/runs/{run}/findings", params={"status": "gap", "limit": 1}).json()["total"]
    assert gaps == detail["totals"]["gap"]  # the register always shows every gap, whatever its review status


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
def test_the_letter_check_and_challenge_rules():
    run = _completed_run()
    if not run:
        pytest.skip("no completed run to test against")
    letter = client.get(f"/api/runs/{run}/letter").json()["body"]
    ok = client.post(f"/api/runs/{run}/letter/check", json={"body": letter}).json()
    assert ok["ok"] and ok["problems"] == [], "the letter the platform writes must pass its own claims check"
    bad = client.post(f"/api/runs/{run}/letter/check", json={"body": letter.replace("## 4.", "All accounts were compliant.\n\n## 4.", 1)}).json()
    assert not bad["ok"]
    # a letter that fails the check cannot be approved, even with every comment filled in
    r = client.post(f"/api/runs/{run}/letter", json={"body": "## 2. Summary\n\nWe found 3 gaps in 12 accounts.", "status": "approved", "author": "Test"})
    assert r.status_code == 400
    # a second reading needs a name and a gap
    assert client.post(f"/api/runs/{run}/findings/1/challenge", json={"requested_by": ""}).status_code == 400
