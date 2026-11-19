"""Checks that the database itself enforces the guardrails. Needs a migrated database
(DATABASE_URL); skipped otherwise. CI runs it against a fresh Postgres."""
import os

import psycopg
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")


@pytest.fixture
def conn():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        yield c
        c.rollback()


def _run_and_check(conn):
    run_id = conn.execute(
        "INSERT INTO audit.runs (request_id, request_source) VALUES ('TEST', 'text') RETURNING run_id"
    ).fetchone()[0]
    conn.execute(
        """INSERT INTO audit.checks (run_id, check_id, question_ref, question_text, check_type,
                                     sample_definition, test_definition, sources)
           VALUES (%s, 'Q1', 'Q1', 'test', 'consent_before_contact', '{}', '{}', '{D4}')""",
        (run_id,))
    return run_id


def _finding(conn, run_id, status, severity=None):
    return conn.execute(
        """INSERT INTO audit.findings (run_id, check_id, account_id, status, severity, reason)
           VALUES (%s, 'Q1', 'A1', %s, %s, 'test finding') RETURNING finding_id""",
        (run_id, status, severity)).fetchone()[0]


def test_evidenced_without_citation_fails_at_commit(conn):
    run_id = _run_and_check(conn)
    _finding(conn, run_id, "evidenced")
    with pytest.raises(psycopg.errors.CheckViolation, match="no citation"):
        conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_evidenced_with_citation_commits(conn):
    run_id = _run_and_check(conn)
    fid = _finding(conn, run_id, "evidenced")
    conn.execute(
        """INSERT INTO audit.citations (finding_id, source_system, source_table, record_key)
           VALUES (%s, 'D4', 'raw.d4_contact_log', '1')""", (fid,))
    conn.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_gap_needs_severity(conn):
    run_id = _run_and_check(conn)
    with pytest.raises(psycopg.errors.CheckViolation):
        _finding(conn, run_id, "gap")


def test_completed_run_findings_are_frozen(conn):
    run_id = _run_and_check(conn)
    fid = _finding(conn, run_id, "cannot_determine")
    conn.execute("UPDATE audit.runs SET status = 'completed' WHERE run_id = %s", (run_id,))
    with pytest.raises(psycopg.errors.CheckViolation, match="completed"):
        conn.execute("UPDATE audit.findings SET status = 'evidenced' WHERE finding_id = %s", (fid,))


def test_agent_reader_cannot_write(conn):
    conn.execute("SET ROLE agent_reader")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("INSERT INTO audit.runs (request_id, request_source) VALUES ('X', 'text')")
