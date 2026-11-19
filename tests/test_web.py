import os

import pytest
from fastapi.testclient import TestClient

from agent.web.app import app

client = TestClient(app)


def test_front_end_is_served():
    r = client.get("/")
    assert r.status_code == 200 and "Audit Evidence Agent" in r.text
    assert client.get("/static/app.js").status_code == 200


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
