"""Database connections. Reads DATABASE_URL from the environment or .env."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
