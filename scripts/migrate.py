"""Apply database changes in a fixed, shared order.

  python scripts/migrate.py            apply pending versioned migrations (db/migrations/V*.sql)
  python scripts/migrate.py --staging  (re)apply repeatable staging scripts (db/staging/R__*.sql)
  python scripts/migrate.py --reset    drop raw/staging/audit and the history table

Versioned migrations are append-only. Once applied anywhere, a file must never change:
the runner stores each file's checksum and refuses to continue if it differs. To change
something, add a new V###__*.sql file. Repeatable scripts are re-run whenever they change.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "db" / "migrations"
STAGING = ROOT / "db" / "staging"
VERSIONED = re.compile(r"^V(\d{3})__[a-z0-9_]+\.sql$")
REPEATABLE = re.compile(r"^R__[a-z0-9_]+\.sql$")

HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS public.schema_history (
    script      text PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('versioned', 'repeatable')),
    checksum    text NOT NULL,
    applied_by  text NOT NULL DEFAULT current_user,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def connect() -> psycopg.Connection:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set. Copy .env.example to .env.")
    return psycopg.connect(url)


def applied(conn) -> dict[str, str]:
    conn.execute(HISTORY_DDL)
    return dict(conn.execute("SELECT script, checksum FROM public.schema_history").fetchall())


def migrate_versioned(conn) -> int:
    done = applied(conn)
    files = sorted(p for p in MIGRATIONS.glob("*.sql"))
    bad = [p.name for p in files if not VERSIONED.match(p.name)]
    if bad:
        sys.exit(f"Bad migration file names (expected V###__snake_case.sql): {bad}")
    versions = [p.name[:4] for p in files]
    dupes = {v for v in versions if versions.count(v) > 1}
    if dupes:
        sys.exit(f"Two migrations share a version number {sorted(dupes)}. "
                 "Someone else took that number; rename yours to the next free one.")

    count = 0
    for path in files:
        digest = checksum(path)
        if path.name in done:
            if done[path.name] != digest:
                sys.exit(f"{path.name} was changed after it was applied. Migrations are "
                         "append-only: revert the edit and add a new migration instead.")
            continue
        with conn.transaction():
            conn.execute(path.read_text())
            conn.execute(
                "INSERT INTO public.schema_history (script, kind, checksum) VALUES (%s, 'versioned', %s)",
                (path.name, digest),
            )
        print(f"  applied {path.name}")
        count += 1
    return count


def apply_staging(conn) -> int:
    done = applied(conn)
    count = 0
    for path in sorted(STAGING.glob("*.sql")):
        if not REPEATABLE.match(path.name):
            sys.exit(f"Bad staging file name (expected R__###_snake_case.sql): {path.name}")
        digest = checksum(path)
        if done.get(path.name) == digest:
            continue
        with conn.transaction():
            conn.execute(path.read_text())
            conn.execute(
                """INSERT INTO public.schema_history (script, kind, checksum)
                   VALUES (%s, 'repeatable', %s)
                   ON CONFLICT (script) DO UPDATE
                   SET checksum = EXCLUDED.checksum, applied_at = now(), applied_by = current_user""",
                (path.name, digest),
            )
        print(f"  applied {path.name}")
        count += 1
    # Make new staging views readable by the agent's read-only role.
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA staging TO agent_reader")
    return count


def reset(conn) -> None:
    url = conn.info.host or ""
    if not (url in ("localhost", "127.0.0.1", "db", "") or url.startswith("/")) and os.environ.get("ALLOW_REMOTE_RESET") != "1":
        sys.exit(f"Refusing to reset non-local database host '{url}'. "
                 "Set ALLOW_REMOTE_RESET=1 if you really mean it.")
    with conn.transaction():
        for schema in ("audit", "staging", "raw"):
            conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.execute("DROP TABLE IF EXISTS public.schema_history")
    print("  dropped raw, staging, audit and schema_history")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staging", action="store_true", help="apply repeatable staging scripts")
    ap.add_argument("--reset", action="store_true", help="drop all project schemas")
    args = ap.parse_args()

    with connect() as conn:
        conn.autocommit = True
        if args.reset:
            reset(conn)
        elif args.staging:
            n = apply_staging(conn)
            print(f"staging: {n} script(s) applied" if n else "staging: up to date")
        else:
            n = migrate_versioned(conn)
            print(f"migrations: {n} applied" if n else "migrations: up to date")


if __name__ == "__main__":
    main()
