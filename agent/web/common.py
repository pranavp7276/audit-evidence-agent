"""Shared by the routers: paths and constants, the read connection and the run lookups."""

import threading
from pathlib import Path
from uuid import UUID

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row

from agent.core.db import database_url
from agent.tools.record_keys import KEY_EXPR

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
EXAMPLES, GAP_KEYS = ROOT / "eval" / "requests", ROOT / "eval" / "gap_keys"
_RUN_LOCK = threading.Lock()  # one run at a time: runs share the tool caches and the reader connection

app = FastAPI(title="Audit evidence platform")

_KEYS = KEY_EXPR  # citation source_table -> the SQL expression that equals its record_key
_PACK_FILES = {"gap_report.csv": "text/csv", "follow_up.csv": "text/csv", "reviews.csv": "text/csv", "agent_trace.csv": "text/csv",
               "rules_and_assumptions.md": "text/markdown", "response_letter.md": "text/markdown", "index.md": "text/markdown"}

# latest review of a finding, as columns r.disposition / r.comment / r.reviewer / r.created_at
_LATEST_REVIEW = """LEFT JOIN LATERAL (SELECT disposition, comment AS review_comment, reviewer, created_at AS reviewed_at
                   FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id ORDER BY x.review_id DESC LIMIT 1) r ON true"""

# latest second reading of a finding, as columns ch.verdict / ch.concern / ch.challenged_at
_LATEST_CHALLENGE = """LEFT JOIN LATERAL (SELECT verdict AS challenge_verdict, concern AS challenge_concern, created_at AS challenged_at
                      FROM audit.finding_challenges y WHERE y.finding_id = f.finding_id ORDER BY y.challenge_id DESC LIMIT 1) ch ON true"""


_conn: psycopg.Connection | None = None
_conn_lock = threading.Lock()


def _q(sql: str, params: tuple = ()) -> list[dict]:
    """Read through one persistent connection (opening a TLS connection per query is what made pages slow).
    Reconnects once if the server dropped it while idle."""
    global _conn
    with _conn_lock:
        for attempt in (1, 2):
            try:
                if _conn is None or _conn.closed:
                    _conn = psycopg.connect(database_url(), row_factory=dict_row, autocommit=True)
                return _conn.execute(sql, params).fetchall()
            except psycopg.OperationalError:
                if attempt == 2:
                    raise
                try:
                    _conn.close()
                except Exception:
                    pass
                _conn = None
    return []


def _one(sql: str, params: tuple = ()) -> dict | None:
    rows = _q(sql, params)
    return rows[0] if rows else None


def _all(sql: str, params: tuple = ()) -> list[dict]:
    return _q(sql, params)


def _run_or_404(run_id: UUID) -> dict:
    run = _one("SELECT * FROM audit.runs WHERE run_id = %s", (run_id,))
    if not run:
        raise HTTPException(404, "Audit request not found")
    return run


def _completed(run_id: UUID) -> dict:
    run = _run_or_404(run_id)
    if run["status"] != "completed":
        raise HTTPException(409, f"The audit is {run['status']}; this is available once it has completed.")
    return run

