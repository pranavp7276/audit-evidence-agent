"""Database connections. Reads DATABASE_URL from the environment or .env."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # the repository root


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")
    return url


@contextmanager
def connect(read_only: bool = False) -> Iterator[psycopg.Connection]:
    """A connection. read_only=True runs as the agent_reader role inside a read-only transaction."""
    with psycopg.connect(database_url(), row_factory=dict_row) as conn:
        if read_only:
            timeout = int(os.environ.get("AGENT_SQL_TIMEOUT_MS", "30000"))
            conn.execute("SET ROLE agent_reader")
            conn.execute(f"SET statement_timeout = {timeout}")
            conn.execute("SET default_transaction_read_only = on")
        yield conn


_reader: psycopg.Connection | None = None


def read_rows(sql: str, params: tuple | dict | None = None) -> list[dict]:
    """Run a read-only query on one reused agent_reader connection (tools make many small queries)."""
    global _reader
    for attempt in (1, 2):
        try:
            if _reader is None or _reader.closed:
                _reader = psycopg.connect(database_url(), row_factory=dict_row, autocommit=True)
                _reader.execute("SET ROLE agent_reader")
                _reader.execute(f"SET statement_timeout = {int(os.environ.get('AGENT_SQL_TIMEOUT_MS', '30000'))}")
                _reader.execute("SET default_transaction_read_only = on")
            return _reader.execute(sql, params).fetchall()
        except psycopg.OperationalError:  # the server dropped an idle connection: reconnect once
            if attempt == 2:
                raise
            try:
                _reader.close()
            except Exception:
                pass
            _reader = None
    return []
