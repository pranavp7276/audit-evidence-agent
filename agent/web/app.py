"""Web platform: upload an audit request, watch it run, review findings with their cited records,
download the evidence pack and the draft response letter, and score a run against a gap key.

  python -m agent serve            then open http://127.0.0.1:8000

Set APP_PASSWORD to require a password (any user name) before anything is served.
All results come from audit.* (docs/decisions.md D-005); this module only reads them, and starts runs
through agent.pipeline, which is the only writer.
"""
from __future__ import annotations

import base64
import io
import os
import secrets
import tempfile
import threading
import zipfile
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from agent import store
from agent.contracts import Request as AuditRequest
from agent.db import connect, read_rows
from agent.pack.writer import build_pack
from agent.parser.request_parser import read_request
from agent.pipeline import process
from agent.tools.warehouse_sql import run_sql

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
EXAMPLES, GAP_KEYS = ROOT / "eval" / "requests", ROOT / "eval" / "gap_keys"
_RUN_LOCK = threading.Lock()  # one run at a time: runs share the tool caches and the reader connection

app = FastAPI(title="Audit evidence pack agent")

# citation source_table -> the column that is its record_key
_KEYS = {"raw.d4_contact_log": "contact_id", "raw.d5": "consent_id", "raw.d10": "recording_id",
         "raw.d11": "verification_id", "raw.d12": "policy_key", "raw.notice_dispatch": "notice_id",
         "raw.holiday_calendar": "_row_no", "raw.collector_roster": "collector_id", "raw.cert_register": "cert_id"}


@app.middleware("http")
async def password_gate(request: Request, call_next):
    expected = os.environ.get("APP_PASSWORD")
    if expected:
        try:
            given = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().partition(":")[2]
        except Exception:
            given = ""
        if not secrets.compare_digest(given, expected):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Audit agent"'})
    return await call_next(request)


def _one(sql: str, params: tuple = ()) -> dict | None:
    with connect() as conn:
        return conn.execute(sql, params).fetchone()


def _all(sql: str, params: tuple = ()) -> list[dict]:
    with connect() as conn:
        return conn.execute(sql, params).fetchall()


def _run_or_404(run_id: UUID) -> dict:
    run = _one("SELECT * FROM audit.runs WHERE run_id = %s", (run_id,))
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/config")
def config() -> dict:
    llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"parser": "llm" if llm else "keyword", "model": os.environ.get("AGENT_MODEL") if llm else None,
            "password_protected": bool(os.environ.get("APP_PASSWORD"))}


@app.get("/api/examples")
def examples() -> list[str]:
    return sorted(p.name for p in EXAMPLES.glob("*") if p.is_file() and p.name != ".gitkeep")


@app.get("/api/examples/{name}")
def example(name: str) -> dict:
    path = EXAMPLES / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return {"name": path.name, "text": path.read_text(encoding="utf-8")}


@app.get("/api/gap-keys")
def gap_keys() -> list[str]:
    return sorted(p.name for p in GAP_KEYS.glob("*.csv"))


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return _all("""
        SELECT r.run_id, r.request_id, r.request_source, r.status, r.started_at, r.finished_at, r.notes, r.agent_version,
               (SELECT count(*) FROM audit.checks c WHERE c.run_id = r.run_id) AS checks,
               count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
               count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
               (SELECT count(DISTINCT account_id) FROM audit.sample_accounts s WHERE s.run_id = r.run_id) AS accounts
        FROM audit.runs r LEFT JOIN audit.findings f USING (run_id)
        GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 100""")


@app.post("/api/runs")
async def create_run(request_id: str = Form(...), text: str = Form(""), accounts: str = Form(""),
                     random_n: int | None = Form(None), file: UploadFile | None = File(None)) -> dict:
    request_id = request_id.strip()
    if not request_id:
        raise HTTPException(400, "Give the request an id, e.g. CO-04.")
    if file is not None and file.filename:
        suffix = Path(file.filename).suffix.lower()
        if suffix not in (".pdf", ".eml", ".txt", ".md", ""):
            raise HTTPException(400, f"Unsupported file type {suffix}; use PDF, .eml or text.")
        folder = Path(tempfile.mkdtemp(prefix="audit-upload-", dir=ROOT / "out" if (ROOT / "out").exists() else None))
        path = folder / Path(file.filename).name
        path.write_bytes(await file.read())
        try:
            request = read_request(path, request_id)
        except Exception as exc:
            raise HTTPException(400, f"Could not read the file: {exc}")
    elif text.strip():
        request = AuditRequest(request_id=request_id, source="text", text=text)
    else:
        raise HTTPException(400, "Upload a request file or paste its text.")
    if not request.text.strip():
        raise HTTPException(400, "The request contains no text (a scanned PDF needs OCR first).")
    sample = [a for a in (t.strip() for t in accounts.replace("\n", ",").split(",")) if a] or None
    run_id = store.start_run(request)

    def work() -> None:
        with _RUN_LOCK:
            try:
                process(run_id, request, accounts=sample, random_n=random_n, log=lambda _: None)
            except Exception:
                pass  # recorded on the run (status failed + notes); the page shows it

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": str(run_id)}


_COUNTS = """count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
             count(f.*) FILTER (WHERE f.status = 'gap') AS gap,
             count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine"""


@app.get("/api/runs/{run_id}")
def run_detail(run_id: UUID) -> dict:
    run = _run_or_404(run_id)
    checks = _all(f"""
        SELECT c.check_id, c.question_ref, c.question_text, c.check_type, c.sources, c.test_definition, c.sample_definition,
               (SELECT count(*) FROM audit.sample_accounts s WHERE s.run_id = c.run_id AND s.check_id = c.check_id) AS accounts,
               {_COUNTS},
               count(DISTINCT f.account_id) FILTER (WHERE f.status = 'gap') AS accounts_with_gaps,
               count(DISTINCT f.account_id) AS accounts_tested
        FROM audit.checks c LEFT JOIN audit.findings f USING (run_id, check_id)
        WHERE c.run_id = %s GROUP BY c.run_id, c.check_id ORDER BY c.check_id""", (run_id,))
    severity = _all("""SELECT severity, count(*) AS findings, count(DISTINCT account_id) AS accounts
                       FROM audit.findings WHERE run_id = %s AND status = 'gap' GROUP BY severity""", (run_id,))
    scale = list(run["severity_scale"])
    severity.sort(key=lambda s: scale.index(s["severity"]) if s["severity"] in scale else len(scale))
    totals = _one(f"""SELECT {_COUNTS}, count(DISTINCT f.account_id) FILTER (WHERE f.status = 'gap') AS accounts_with_gaps
                      FROM audit.findings f WHERE f.run_id = %s""", (run_id,))
    return {"run": run, "checks": checks, "severity": severity, "totals": totals,
            "tested_checks": sum(1 for c in checks if c["accounts_tested"] > 0)}


@app.get("/api/runs/{run_id}/findings")
def findings(run_id: UUID, check_id: str | None = None, status: str | None = None, account: str | None = None,
             severity: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    run = _run_or_404(run_id)
    where, params = ["f.run_id = %s"], [run_id]
    for col, val in (("f.check_id", check_id), ("f.status", status), ("f.severity", severity)):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    if account:
        where.append("f.account_id ILIKE %s")
        params.append(f"%{account.strip()}%")
    clause = " AND ".join(where)
    scale = list(run["severity_scale"])
    total = _one(f"SELECT count(*) AS n FROM audit.findings f WHERE {clause}", tuple(params))["n"]
    rows = _all(f"""
        SELECT f.finding_id, f.check_id, c.question_ref, c.check_type, f.account_id, f.subject_ref, f.status, f.severity,
               f.reason, f.evidence_query,
               COALESCE((SELECT jsonb_agg(to_jsonb(ci) - 'finding_id' ORDER BY ci.citation_id)
                         FROM audit.citations ci WHERE ci.finding_id = f.finding_id), '[]') AS citations
        FROM audit.findings f JOIN audit.checks c USING (run_id, check_id)
        WHERE {clause}
        ORDER BY (f.status <> 'gap'), COALESCE(array_position(%s::text[], f.severity), 99), f.check_id, f.account_id,
                 f.subject_ref NULLS FIRST
        LIMIT %s OFFSET %s""", (*params, scale, max(1, min(limit, 500)), max(0, offset)))
    return {"total": total, "rows": rows}


@app.post("/api/sql")
async def sql(request: Request) -> dict:
    """Ad-hoc read-only SELECT through the warehouse SQL tool (read-only role, keyword filter, timeout)."""
    body = await request.json()
    try:
        out = run_sql(str(body.get("query", "")), max_rows=int(body.get("max_rows", 500)))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # database errors: show the message, not a stack trace
        diag = getattr(exc, "diag", None)
        raise HTTPException(400, (diag.message_primary if diag and diag.message_primary else str(exc)))
    cols = list(out["rows"][0]) if out["rows"] else []
    return {"columns": cols, "rows": [list(r.values()) for r in out["rows"]], "truncated": out["truncated"]}


@app.get("/api/record")
def record(table: str, key: str) -> dict:
    """The full source row behind a citation, read as the read-only role from the raw layer."""
    col = _KEYS.get(table)
    if not col:
        raise HTTPException(400, "Unknown source table")
    schema, name = table.split(".")
    rows = read_rows(f'SELECT * FROM "{schema}"."{name}" WHERE "{col}"::text = %s LIMIT 1', (key,))
    if not rows:
        raise HTTPException(404, "Record not found")
    return {"table": table, "key_column": col, "record": rows[0]}


def _pack(run_id: UUID) -> Path:
    run = _run_or_404(run_id)
    if run["status"] != "completed":
        raise HTTPException(409, f"The run is {run['status']}; the pack is available once it has completed.")
    return Path(build_pack(run_id))


@app.get("/api/runs/{run_id}/letter")
def letter(run_id: UUID) -> dict:
    return {"markdown": (_pack(run_id) / "response_letter.md").read_text(encoding="utf-8")}


@app.get("/api/runs/{run_id}/index")
def pack_index(run_id: UUID) -> dict:
    return {"markdown": (_pack(run_id) / "index.md").read_text(encoding="utf-8")}


@app.get("/api/runs/{run_id}/gap_report.csv")
def gap_report(run_id: UUID) -> FileResponse:
    return FileResponse(_pack(run_id) / "gap_report.csv", media_type="text/csv", filename=f"gap_report_{run_id}.csv")


@app.get("/api/runs/{run_id}/pack.zip")
def pack_zip(run_id: UUID) -> Response:
    folder = _pack(run_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(folder.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(folder).as_posix())
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="evidence_pack_{run_id}.zip"'})


@app.post("/api/runs/{run_id}/score")
async def score_run(run_id: UUID, key_name: str = Form(""), account_col: str = Form("account_id"),
                    check_col: str = Form("question_ref"), file: UploadFile | None = File(None)) -> JSONResponse:
    from eval.score import load_gap_key, load_reported, score

    run = _run_or_404(run_id)
    if run["status"] != "completed":
        raise HTTPException(409, "Score a run once it has completed.")
    if file is not None and file.filename:
        path = Path(tempfile.mkdtemp(prefix="gapkey-")) / "key.csv"
        path.write_bytes(await file.read())
    elif key_name:
        path = GAP_KEYS / Path(key_name).name
        if not path.is_file():
            raise HTTPException(404, "Unknown gap key")
    else:
        raise HTTPException(400, "Choose a gap key or upload one.")
    try:
        truth = load_gap_key(path, account_col, check_col, None, "gap")
    except SystemExit as exc:
        raise HTTPException(400, str(exc))
    reported, unsupported = load_reported(str(run_id), "question_ref")
    s = score(truth, reported, unsupported)
    return JSONResponse({**asdict(s), "passes": s.passes})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
