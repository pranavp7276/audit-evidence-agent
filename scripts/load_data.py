"""Load source files into the raw schema, exactly as provided.

Every column lands as TEXT, so nothing is silently coerced (a timestamp with an odd zone
suffix stays exactly as the source wrote it). Typing and time-zone handling happen once,
in db/staging. Each load drops and recreates its table, so it is safe to re-run.

  python scripts/load_data.py              load everything in data/manifest.yaml
  python scripts/load_data.py d4_contact_log cert_register   load only these tables
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

import psycopg
import yaml
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def clean_column(name: str, seen: set[str]) -> str:
    col = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower() or "col"
    if col[0].isdigit():
        col = f"c_{col}"
    base, i = col, 2
    while col in seen or col in ("_row_no", "_source_file"):
        col, i = f"{base}_{i}", i + 1
    seen.add(col)
    return col


def read_rows(path: Path, sheet: str | None) -> tuple[list[str], Iterator[list[str | None]]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f))
        def gen_csv() -> Iterator[list[str | None]]:
            with path.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    yield [v if v != "" else None for v in row]
        return header, gen_csv()
    if suffix in (".json", ".jsonl"):
        if suffix == ".json":
            records = json.loads(path.read_text(encoding="utf-8"))
        else:
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        header = list(dict.fromkeys(k for r in records for k in r))
        def gen() -> Iterator[list[str | None]]:
            for r in records:
                yield [None if r.get(k) is None else
                       (json.dumps(r[k]) if isinstance(r[k], (dict, list)) else str(r[k])) for k in header]
        return header, gen()
    if suffix in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            sys.exit("openpyxl is needed for Excel files: pip install openpyxl")
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = [str(h) if h is not None else "" for h in next(rows)]
        return header, ([None if v is None else str(v) for v in row] for row in rows)
    sys.exit(f"Unsupported file type: {path}")


def load_one(conn, entry: dict) -> None:
    table, path = entry["table"], DATA / entry["file"]
    if not path.exists():
        print(f"  skip  {table:<22} file not found: data/{entry['file']}")
        return
    header, rows = read_rows(path, entry.get("sheet"))
    seen: set[str] = set()
    cols = [clean_column(h, seen) for h in header]
    ident = sql.Identifier("raw", table)

    with conn.transaction():
        conn.execute(sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(ident))
        conn.execute(sql.SQL("CREATE TABLE {} (_row_no bigint PRIMARY KEY, _source_file text NOT NULL, {})").format(
            ident, sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)))
        copy_sql = sql.SQL("COPY {} ({}) FROM STDIN").format(
            ident, sql.SQL(", ").join(map(sql.Identifier, ["_row_no", "_source_file", *cols])))
        n = 0
        with conn.cursor().copy(copy_sql) as cp:
            for n, row in enumerate(rows, start=1):
                row = list(row)[: len(cols)] + [None] * (len(cols) - len(row))
                cp.write_row([n, entry["file"], *row])
        desc = entry.get("description") or ""
        conn.execute(sql.SQL("COMMENT ON TABLE {} IS {}").format(
            ident, sql.Literal(f"[{entry.get('source_system')}] {desc} (from data/{entry['file']})")))
        conn.execute(sql.SQL("GRANT SELECT ON {} TO agent_reader").format(ident))
    renamed = [f"{h!r}->{c}" for h, c in zip(header, cols) if h != c]
    print(f"  load  {table:<22} {n:>10,} rows, {len(cols)} cols"
          + (f"  (renamed: {', '.join(renamed[:5])}{' ...' if len(renamed) > 5 else ''})" if renamed else ""))


def main(only: Iterable[str]) -> None:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL") or sys.exit("DATABASE_URL is not set. Copy .env.example to .env.")
    manifest = yaml.safe_load((DATA / "manifest.yaml").read_text())
    entries = manifest["datasets"]
    only = set(only)
    if only:
        unknown = only - {e["table"] for e in entries}
        if unknown:
            sys.exit(f"Not in manifest: {sorted(unknown)}")
        entries = [e for e in entries if e["table"] in only]
    with psycopg.connect(url, autocommit=True) as conn:
        for entry in entries:
            load_one(conn, entry)
        # Reloading a raw table drops the staging views built on it (CASCADE), so mark every
        # staging script as not applied; `make load` re-runs them straight after.
        conn.execute("""DO $$ BEGIN
            IF to_regclass('public.schema_history') IS NOT NULL THEN
                DELETE FROM public.schema_history WHERE kind = 'repeatable';
            END IF; END $$""")


if __name__ == "__main__":
    main(sys.argv[1:])
