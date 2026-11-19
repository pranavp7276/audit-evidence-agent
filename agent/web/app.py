"""Web platform for collections auditors: take in an audit request, confirm how its questions were read,
run the evidence tests, review every finding with its cited records, follow up what could not be
determined, and release a cited response letter and evidence pack.

  python -m agent serve            then open http://127.0.0.1:8000

Set APP_PASSWORD to require a password (any user name) before anything is served.
Findings come from audit.* and are never changed (docs/decisions.md D-005). What an auditor adds (reviews,
management comments, letter versions) is stored in separate append-only tables (V003). Runs go through
agent.pipeline, the only writer of findings.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import secrets
import tempfile
import threading
import zipfile
from dataclasses import asdict
from datetime import date
from pathlib import Path
from uuid import UUID

import psycopg
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

from agent import store
from agent.contracts import CheckSpec, CheckType
from agent.contracts import Request as AuditRequest
from agent.db import connect, database_url, read_rows
from agent.pack.writer import DISPOSITIONS, build_pack, generate_letter
from agent.parser.request_parser import _SOURCES, parse_checks, parse_sample, read_request
from agent.pipeline import MAX_SAMPLE, contacted_accounts, process
from agent.tools.warehouse_sql import run_sql
from agent.web.rules import ASSUMPTIONS, CHECK_INFO, SOURCES, STATUS_MEANING

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).parent / "static"
EXAMPLES, GAP_KEYS = ROOT / "eval" / "requests", ROOT / "eval" / "gap_keys"
_RUN_LOCK = threading.Lock()  # one run at a time: runs share the tool caches and the reader connection

app = FastAPI(title="Audit evidence platform")

# citation source_table -> the column that is its record_key
_KEYS = {"raw.d4_contact_log": "contact_id", "raw.d5": "consent_id", "raw.d10": "recording_id",
         "raw.d11": "verification_id", "raw.d12": "policy_key", "raw.notice_dispatch": "notice_id",
         "raw.holiday_calendar": "_row_no", "raw.collector_roster": "collector_id", "raw.cert_register": "cert_id"}
_PACK_FILES = {"gap_report.csv": "text/csv", "follow_up.csv": "text/csv", "reviews.csv": "text/csv",
               "rules_and_assumptions.md": "text/markdown", "response_letter.md": "text/markdown", "index.md": "text/markdown"}

# latest review of a finding, as columns r.disposition / r.comment / r.reviewer / r.created_at
_LATEST_REVIEW = """LEFT JOIN LATERAL (SELECT disposition, comment AS review_comment, reviewer, created_at AS reviewed_at
                   FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id ORDER BY x.review_id DESC LIMIT 1) r ON true"""


@app.middleware("http")
async def password_gate(request: Request, call_next):
    expected = os.environ.get("APP_PASSWORD")
    if expected:
        try:
            given = base64.b64decode(request.headers.get("authorization", "")[6:]).decode().partition(":")[2]
        except Exception:
            given = ""
        if not secrets.compare_digest(given, expected):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Audit platform"'})
    return await call_next(request)


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


# ---------------------------------------------------------------- configuration and reference

@app.get("/api/config")
def config() -> dict:
    llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"parser": "llm" if llm else "keyword", "model": os.environ.get("AGENT_MODEL") if llm else None,
            "password_protected": bool(os.environ.get("APP_PASSWORD")), "sla_minutes": 120,
            "check_types": {k: v["title"] for k, v in CHECK_INFO.items()}}


@app.get("/api/rules")
def rules() -> dict:
    policy = read_rows("SELECT policy_key, policy_value, unit, applies_to, note FROM staging.d12_policy ORDER BY source_row")
    return {"checks": CHECK_INFO, "status_meaning": STATUS_MEANING, "dispositions": DISPOSITIONS,
            "assumptions": [{"topic": k, "text": v} for k, v in ASSUMPTIONS], "policy": policy}


@app.get("/api/data-sources")
def data_sources() -> list[dict]:
    out = []
    for label, view, col, tz in SOURCES:
        sel = f"count(*) AS n, min({col}) AS first, max({col}) AS last" if col else "count(*) AS n, NULL AS first, NULL AS last"
        row = read_rows(f"SELECT {sel} FROM {view}")[0]
        out.append({"source": label, "view": view, "rows": row["n"], "first": row["first"], "last": row["last"], "timezone": tz})
    return out


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


# ---------------------------------------------------------------- intake: preview, then run

async def _request_from_form(request_id: str, text: str, source: str, file: UploadFile | None) -> AuditRequest:
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
        request = AuditRequest(request_id=request_id, source=source if source in ("pdf", "email", "text") else "text", text=text)
    else:
        raise HTTPException(400, "Upload the audit request or paste its text.")
    if not request.text.strip():
        raise HTTPException(400, "The request contains no text (a scanned PDF needs OCR first).")
    return request


@app.post("/api/requests/preview")
async def preview(request_id: str = Form("PREVIEW"), text: str = Form(""), source: str = Form("text"),
                  file: UploadFile | None = File(None)) -> dict:
    """Read the request and show how it would be tested, without running anything."""
    request = await _request_from_form(request_id.strip() or "PREVIEW", text, source, file)
    try:
        checks, scale = parse_checks(request)
    except Exception as exc:
        raise HTTPException(400, f"Could not interpret the request: {exc}")
    stated = parse_sample(request.text)
    accounts = stated["accounts"]
    known = {r["account_id"] for r in read_rows(
        "SELECT DISTINCT account_id FROM staging.d4_contacts WHERE account_id = ANY(%s)", (accounts,))} if accounts else set()
    rows = [{"check_id": c.check_id, "question_ref": c.question_ref, "question_text": c.question_text,
             "check_type": c.check_type.value, "severity": c.test.get("severity"), "sources": [s.value for s in c.sources]}
            for c in checks]
    period = stated["period"]
    return {"source": request.source, "text": request.text, "checks": rows, "scale": scale, "accounts": len(accounts),
            "unknown_accounts": [a for a in accounts if a not in known][:100], "unknown_count": len(accounts) - len(known),
            "parser": "llm" if os.environ.get("ANTHROPIC_API_KEY") else "keyword",
            "instruction": not re.search(r"^\s*Q\d+\s*[.:)]", request.text, re.MULTILINE),
            "period": period, "size": stated["size"], "eligible": contacted_accounts(period), "max_sample": MAX_SAMPLE}


@app.get("/api/population")
def population(start: str = "", end: str = "") -> dict:
    """How many accounts had a contact in a period (India calendar days, end exclusive)."""
    try:
        period = {"start": start, "end": end, "label": ""} if start and end else None
        return {"eligible": contacted_accounts(period)}
    except ValueError:
        raise HTTPException(400, "Dates must look like 2026-10-01.")


@app.post("/api/runs")
async def create_run(request_id: str = Form(...), text: str = Form(""), source: str = Form("text"), lender: str = Form(""),
                     response_due: str = Form(""), created_by: str = Form(""), accounts: str = Form(""),
                     random_n: int | None = Form(None), checks: str = Form(""), scale: str = Form(""),
                     period_start: str = Form(""), period_end: str = Form(""), period_label: str = Form(""),
                     sample_size: int | None = Form(None), file: UploadFile | None = File(None)) -> dict:
    request_id = request_id.strip()
    if not request_id:
        raise HTTPException(400, "Give the request an id, e.g. CO-04.")
    request = await _request_from_form(request_id, text, source, file)
    specs = None
    if checks.strip():  # the auditor's reviewed interpretation
        try:
            specs = [CheckSpec(check_id=c["check_id"], question_ref=c["question_ref"], question_text=c["question_text"],
                               check_type=CheckType(c["check_type"]), sample={}, sources=_SOURCES[CheckType(c["check_type"])],
                               test={"severity": c["severity"]} if c.get("severity") else {}) for c in json.loads(checks)]
        except Exception as exc:
            raise HTTPException(400, f"The reviewed checks are not valid: {exc}")
    labels = json.loads(scale) if scale.strip() else None
    sample = [a for a in (t.strip() for t in accounts.replace("\n", ",").split(",")) if a] or None
    period = None
    if period_start and period_end:
        try:
            if date.fromisoformat(period_start) >= date.fromisoformat(period_end):
                raise ValueError
        except ValueError:
            raise HTTPException(400, "The period needs a start date before its end date (the end day is not included).")
        period = {"start": period_start, "end": period_end, "label": period_label.strip() or f"{period_start} to {period_end}"}
    run_id = store.start_run(request, lender=lender.strip(), response_due=response_due.strip(), created_by=created_by.strip())

    def work() -> None:
        with _RUN_LOCK:
            try:
                process(run_id, request, accounts=sample, random_n=random_n, log=lambda _: None, checks=specs, scale=labels,
                        period=period, size=sample_size)
            except Exception:
                pass  # recorded on the run (status failed + notes); the page shows it

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": str(run_id)}


# ---------------------------------------------------------------- engagements and summaries

@app.get("/api/runs")
def list_runs() -> list[dict]:
    return _all("""
        SELECT r.run_id, r.request_id, r.lender, r.response_due, r.created_by, r.status, r.started_at, r.finished_at, r.notes,
               (SELECT count(*) FROM audit.checks c WHERE c.run_id = r.run_id) AS checks,
               count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
               count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
               count(f.*) FILTER (WHERE f.status = 'gap' AND r2.disposition IS NOT NULL AND r2.disposition <> 'open') AS gaps_reviewed,
               (SELECT count(DISTINCT account_id) FROM audit.sample_accounts s WHERE s.run_id = r.run_id) AS accounts,
               (SELECT status FROM audit.letters l WHERE l.run_id = r.run_id ORDER BY version DESC LIMIT 1) AS letter_status
        FROM audit.runs r
        LEFT JOIN audit.findings f USING (run_id)
        LEFT JOIN LATERAL (SELECT disposition FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id
                           ORDER BY x.review_id DESC LIMIT 1) r2 ON true
        GROUP BY r.run_id ORDER BY r.started_at DESC LIMIT 100""")


_COUNTS = """count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
             count(f.*) FILTER (WHERE f.status = 'gap') AS gap,
             count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine"""


@app.get("/api/runs/{run_id}")
def run_detail(run_id: UUID) -> dict:
    run = _run_or_404(run_id)
    checks = _all(f"""
        SELECT c.check_id, c.question_ref, c.question_text, c.check_type, c.sources, c.test_definition, c.sample_definition,
               (SELECT count(*) FROM audit.sample_accounts s WHERE s.run_id = c.run_id AND s.check_id = c.check_id) AS accounts,
               {_COUNTS}
        FROM audit.checks c LEFT JOIN audit.findings f USING (run_id, check_id)
        WHERE c.run_id = %s GROUP BY c.run_id, c.check_id ORDER BY c.check_id""", (run_id,))
    per_acct = {r["check_id"]: r for r in _all("""
        SELECT check_id, count(*) AS accounts_tested, count(*) FILTER (WHERE g) AS accounts_gap,
               count(*) FILTER (WHERE NOT g AND e) AS accounts_ok, count(*) FILTER (WHERE NOT g AND NOT e) AS accounts_unknown
        FROM (SELECT check_id, account_id, bool_or(status = 'gap') AS g, bool_or(status = 'evidenced') AS e
              FROM audit.findings WHERE run_id = %s GROUP BY check_id, account_id) t GROUP BY check_id""", (run_id,))}
    for c in checks:
        c.update(per_acct.get(c["check_id"], {"accounts_tested": 0, "accounts_gap": 0, "accounts_ok": 0, "accounts_unknown": 0}))
        c["title"] = CHECK_INFO[c["check_type"]]["title"]
    scale = list(run["severity_scale"])
    severity = _all("""SELECT severity, count(*) AS findings, count(DISTINCT account_id) AS accounts
                       FROM audit.findings WHERE run_id = %s AND status = 'gap' GROUP BY severity""", (run_id,))
    severity.sort(key=lambda s: scale.index(s["severity"]) if s["severity"] in scale else len(scale))
    totals = _one(f"""SELECT {_COUNTS}, count(DISTINCT f.account_id) FILTER (WHERE f.status = 'gap') AS accounts_with_gaps
                      FROM audit.findings f WHERE f.run_id = %s""", (run_id,))
    sample = _one("SELECT count(DISTINCT account_id) AS n FROM audit.sample_accounts WHERE run_id = %s", (run_id,))["n"]
    no_data = _all("""SELECT s.account_id FROM (SELECT DISTINCT account_id FROM audit.sample_accounts WHERE run_id = %s) s
                      WHERE NOT EXISTS (SELECT 1 FROM staging.d4_contacts c WHERE c.account_id = s.account_id)
                      ORDER BY 1 LIMIT 50""", (run_id,))
    collectors = _all("""
        SELECT c.collector_id, k.agency, count(*) AS gaps, count(DISTINCT f.account_id) AS accounts,
               array_agg(DISTINCT ck.question_ref ORDER BY ck.question_ref) AS questions
        FROM audit.findings f JOIN audit.checks ck USING (run_id, check_id)
        JOIN staging.d4_contacts c ON c.contact_id = f.subject_ref
        LEFT JOIN staging.collectors k ON k.collector_id = c.collector_id
        WHERE f.run_id = %s AND f.status = 'gap' GROUP BY c.collector_id, k.agency ORDER BY gaps DESC, c.collector_id LIMIT 8""", (run_id,))
    months = _all("""
        SELECT to_char(date_trunc('month', c.contact_ts_utc), 'YYYY-MM') AS month, count(*) AS gaps
        FROM audit.findings f JOIN staging.d4_contacts c ON c.contact_id = f.subject_ref
        WHERE f.run_id = %s AND f.status = 'gap' GROUP BY 1 ORDER BY 1""", (run_id,))
    review = _all(f"""SELECT f.status, COALESCE(r.disposition, 'open') AS disposition, count(*) AS n
                      FROM audit.findings f {_LATEST_REVIEW} WHERE f.run_id = %s AND f.status IN ('gap', 'cannot_determine')
                      GROUP BY 1, 2""", (run_id,))
    letter = _one("SELECT version, status, author, created_at FROM audit.letters WHERE run_id = %s ORDER BY version DESC LIMIT 1", (run_id,))
    responses = _one("SELECT count(DISTINCT question_ref) AS n FROM audit.question_responses WHERE run_id = %s", (run_id,))["n"]
    return {"run": run, "checks": checks, "severity": severity, "totals": totals,
            "tested_checks": sum(1 for c in checks if c["accounts_tested"] > 0),
            "coverage": {"sampled": sample, "no_data": [r["account_id"] for r in no_data]},
            "collectors": collectors, "months": months, "review": review, "letter": letter,
            "responses": responses, "questions": len({c["question_ref"] for c in checks})}


@app.get("/api/runs/{run_id}/findings")
def findings(run_id: UUID, check_id: str | None = None, question: str | None = None, status: str | None = None,
             account: str | None = None, severity: str | None = None, disposition: str | None = None,
             limit: int = 50, offset: int = 0) -> dict:
    run = _run_or_404(run_id)
    where, params = ["f.run_id = %s"], [run_id]
    for col, val in (("f.check_id", check_id), ("c.question_ref", question), ("f.status", status), ("f.severity", severity)):
        if val:
            where.append(f"{col} = %s")
            params.append(val)
    if disposition:
        where.append("COALESCE(r.disposition, 'open') = %s")
        params.append(disposition)
    if account:
        where.append("f.account_id ILIKE %s")
        params.append(f"%{account.strip()}%")
    clause = " AND ".join(where)
    base = f"FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) {_LATEST_REVIEW} WHERE {clause}"
    total = _one(f"SELECT count(*) AS n {base}", tuple(params))["n"]
    rows = _all(f"""
        SELECT f.finding_id, f.check_id, c.question_ref, c.check_type, f.account_id, f.subject_ref, f.status, f.severity,
               f.reason, f.evidence_query, COALESCE(r.disposition, 'open') AS disposition, r.review_comment, r.reviewer, r.reviewed_at,
               COALESCE((SELECT jsonb_agg(to_jsonb(ci) - 'finding_id' ORDER BY ci.citation_id)
                         FROM audit.citations ci WHERE ci.finding_id = f.finding_id), '[]') AS citations
        {base}
        ORDER BY (f.status <> 'gap'), COALESCE(array_position(%s::text[], f.severity), 99), f.check_id, f.account_id,
                 f.subject_ref NULLS FIRST
        LIMIT %s OFFSET %s""", (*params, list(run["severity_scale"]), max(1, min(limit, 500)), max(0, offset)))
    return {"total": total, "rows": rows}


@app.post("/api/runs/{run_id}/reviews")
async def add_reviews(run_id: UUID, request: Request) -> dict:
    """Record a reviewer's decision on one or more findings. Adds rows; never edits or removes a finding."""
    _completed(run_id)
    body = await request.json()
    ids, disp = [int(i) for i in body.get("finding_ids", [])], body.get("disposition")
    reviewer, comment = str(body.get("reviewer", "")).strip(), str(body.get("comment", "")).strip()
    if not ids:
        raise HTTPException(400, "Select at least one finding.")
    if disp not in DISPOSITIONS:
        raise HTTPException(400, "Unknown review decision.")
    if not reviewer:
        raise HTTPException(400, "Enter your name before reviewing, so the decision can be attributed.")
    if disp in ("disputed", "remediation_planned") and not comment:
        raise HTTPException(400, "A comment is required when disputing a gap or planning remediation.")
    with connect() as conn, conn.transaction():
        found = {r["finding_id"] for r in conn.execute(
            "SELECT finding_id FROM audit.findings WHERE run_id = %s AND finding_id = ANY(%s)", (run_id, ids))}
        if found != set(ids):
            raise HTTPException(400, "Some findings do not belong to this audit.")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO audit.finding_reviews (run_id, finding_id, reviewer, disposition, comment) VALUES (%s, %s, %s, %s, %s)",
                            [(run_id, i, reviewer, disp, comment or None) for i in ids])
    return {"saved": len(ids)}


@app.get("/api/runs/{run_id}/responses")
def responses(run_id: UUID) -> dict:
    _run_or_404(run_id)
    return {r["question_ref"]: r for r in _all(
        "SELECT DISTINCT ON (question_ref) question_ref, body, author, created_at FROM audit.question_responses "
        "WHERE run_id = %s ORDER BY question_ref, response_id DESC", (run_id,))}


@app.put("/api/runs/{run_id}/responses/{question_ref}")
async def put_response(run_id: UUID, question_ref: str, request: Request) -> dict:
    _completed(run_id)
    body = await request.json()
    text, author = str(body.get("body", "")).strip(), str(body.get("author", "")).strip()
    if not author:
        raise HTTPException(400, "Enter your name first.")
    if not text:
        raise HTTPException(400, "Write the management comment first.")
    with connect() as conn:
        conn.execute("INSERT INTO audit.question_responses (run_id, question_ref, author, body) VALUES (%s, %s, %s, %s)",
                     (run_id, question_ref, author, text))
    return {"saved": True}


# ---------------------------------------------------------------- accounts

@app.get("/api/runs/{run_id}/accounts")
def accounts(run_id: UUID, q: str = "", only_gaps: bool = False, limit: int = 100, offset: int = 0) -> dict:
    _run_or_404(run_id)
    having = "HAVING count(f.*) FILTER (WHERE f.status = 'gap') > 0" if only_gaps else ""
    rows = _all(f"""
        SELECT s.account_id, count(f.*) FILTER (WHERE f.status = 'gap') AS gaps,
               count(f.*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
               count(f.*) FILTER (WHERE f.status = 'evidenced') AS evidenced,
               COALESCE(array_agg(DISTINCT c.question_ref ORDER BY c.question_ref) FILTER (WHERE f.status = 'gap'), '{{}}') AS gap_questions
        FROM (SELECT DISTINCT account_id FROM audit.sample_accounts WHERE run_id = %s AND account_id ILIKE %s) s
        LEFT JOIN audit.findings f ON f.run_id = %s AND f.account_id = s.account_id
        LEFT JOIN audit.checks c ON c.run_id = f.run_id AND c.check_id = f.check_id
        GROUP BY s.account_id {having} ORDER BY gaps DESC, s.account_id LIMIT %s OFFSET %s""",
                (run_id, f"%{q.strip()}%", run_id, max(1, min(limit, 500)), max(0, offset)))
    total = _one(f"""SELECT count(*) AS n FROM (SELECT s.account_id FROM (SELECT DISTINCT account_id FROM audit.sample_accounts
                     WHERE run_id = %s AND account_id ILIKE %s) s LEFT JOIN audit.findings f ON f.run_id = %s AND f.account_id = s.account_id
                     GROUP BY s.account_id {having}) t""", (run_id, f"%{q.strip()}%", run_id))["n"]
    return {"total": total, "rows": rows}


@app.get("/api/runs/{run_id}/accounts/{account_id}")
def account_file(run_id: UUID, account_id: str) -> dict:
    """One borrower's file: the findings for this audit and a UTC timeline of every record involved."""
    _run_or_404(run_id)
    fs = _all(f"""
        SELECT f.finding_id, f.check_id, c.question_ref, c.check_type, f.account_id, f.subject_ref, f.status, f.severity, f.reason,
               COALESCE(r.disposition, 'open') AS disposition, r.review_comment, r.reviewer,
               COALESCE((SELECT jsonb_agg(to_jsonb(ci) - 'finding_id' ORDER BY ci.citation_id)
                         FROM audit.citations ci WHERE ci.finding_id = f.finding_id), '[]') AS citations
        FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) {_LATEST_REVIEW}
        WHERE f.run_id = %s AND f.account_id = %s ORDER BY (f.status <> 'gap'), f.check_id, f.subject_ref NULLS FIRST""", (run_id, account_id))
    flag: dict[str, str] = {}
    prio = {"gap": 3, "cannot_determine": 2, "evidenced": 1}
    for f in fs:
        for c in f["citations"]:
            if prio[f["status"]] > prio.get(flag.get(c["record_key"], ""), 0):
                flag[c["record_key"]] = f["status"]
        if f["subject_ref"] and prio[f["status"]] > prio.get(flag.get(f["subject_ref"], ""), 0):
            flag[f["subject_ref"]] = f["status"]
    p = (account_id,)
    events: list[dict] = []
    for r in read_rows("SELECT * FROM staging.d4_contacts WHERE account_id = %s", p):
        what = {"call": "Call", "whatsapp": "WhatsApp message", "sms": "SMS"}.get(r["channel"], r["channel"])
        events.append({"ts": r["contact_ts_utc"], "kind": r["channel"], "id": r["contact_id"], "source": "D4 contact log",
                       "title": f"{what} ({r['outcome'].replace('_', ' ')})", "src_ts": r["contact_ts_src"], "tz": r["contact_ts_src_tz"],
                       "detail": f"Collector {r['collector_id']}" + ("; dues disclosed" if r["dues_disclosed"] else "")})
    for r in read_rows("SELECT * FROM staging.d5_consents WHERE account_id = %s", p):
        events.append({"ts": r["consent_ts_utc"], "kind": "consent", "id": r["consent_id"], "source": "D5 consent registry",
                       "title": f"Consent {r['status']} for {r['channel']}", "src_ts": r["consent_ts_src"], "tz": r["consent_ts_src_tz"],
                       "detail": f"Captured via {r['capture_source']}"})
    for r in read_rows("SELECT * FROM staging.d11_verifications WHERE account_id = %s", p):
        events.append({"ts": r["verified_ts_utc"], "kind": "verification", "id": r["verification_id"], "source": "D11 identity verification",
                       "title": f"Identity verification {r['result']}", "src_ts": r["verified_ts_src"], "tz": r["verified_ts_src_tz"],
                       "detail": f"Method {r['method']}; call {r['contact_id']}"})
    for r in read_rows("SELECT * FROM staging.d10_recordings WHERE account_id = %s", p):
        events.append({"ts": r["recorded_ts_utc"], "kind": "recording", "id": r["recording_id"], "source": "D10 recording store",
                       "title": "Call recording stored", "src_ts": r["recorded_ts_src"], "tz": r["recorded_ts_src_tz"],
                       "detail": f"{r['duration_sec']} s; call {r['contact_id']}"})
    for r in read_rows("SELECT * FROM staging.notices WHERE account_id = %s", p):
        events.append({"ts": r["trigger_date"], "kind": "notice", "id": r["notice_id"], "source": "Notice dispatch history",
                       "title": f"{r['notice_type'].replace('_', ' ').title()}: triggered", "src_ts": str(r["trigger_date"]), "tz": "date",
                       "detail": f"Dispatched {r['dispatch_date']}; served {r['service_date']}", "all_day": True})
    for e in events:
        e["flag"] = flag.get(e["id"])
        e["ts"] = e["ts"].isoformat() if hasattr(e["ts"], "isoformat") else str(e["ts"])
    events.sort(key=lambda e: (e["ts"], e["id"]))
    return {"account_id": account_id, "findings": fs, "events": events}


# ---------------------------------------------------------------- response letter

@app.get("/api/runs/{run_id}/letter")
def letter(run_id: UUID) -> dict:
    _completed(run_id)
    versions = _all("SELECT version, status, author, note, created_at FROM audit.letters WHERE run_id = %s ORDER BY version DESC", (run_id,))
    latest = _one("SELECT * FROM audit.letters WHERE run_id = %s ORDER BY version DESC LIMIT 1", (run_id,))
    if latest:
        return {"body": latest["body"], "status": latest["status"], "version": latest["version"], "author": latest["author"],
                "created_at": latest["created_at"], "saved": True, "versions": versions}
    return {"body": generate_letter(run_id), "status": "draft", "version": 0, "author": None, "created_at": None, "saved": False, "versions": []}


@app.get("/api/runs/{run_id}/letter/version/{version}")
def letter_version(run_id: UUID, version: int) -> dict:
    row = _one("SELECT * FROM audit.letters WHERE run_id = %s AND version = %s", (run_id, version))
    if not row:
        raise HTTPException(404, "No such version")
    return row


@app.get("/api/runs/{run_id}/letter/generate")
def letter_generate(run_id: UUID) -> dict:
    _completed(run_id)
    return {"body": generate_letter(run_id)}


@app.post("/api/runs/{run_id}/letter")
async def save_letter(run_id: UUID, request: Request) -> dict:
    """Save a new letter version. Approval needs every management comment filled in."""
    _completed(run_id)
    body = await request.json()
    text, status = str(body.get("body", "")), body.get("status", "draft")
    author, note = str(body.get("author", "")).strip(), str(body.get("note", "")).strip()
    if status not in ("draft", "in_review", "approved"):
        raise HTTPException(400, "Unknown letter status.")
    if not author:
        raise HTTPException(400, "Enter your name first.")
    if not text.strip():
        raise HTTPException(400, "The letter is empty.")
    if status == "approved" and "[To be completed" in text:
        raise HTTPException(400, "The letter still has placeholders ('[To be completed by management]'). Complete them before approving.")
    with connect() as conn, conn.transaction():
        v = conn.execute("SELECT COALESCE(max(version), 0) + 1 AS v FROM audit.letters WHERE run_id = %s", (run_id,)).fetchone()["v"]
        conn.execute("INSERT INTO audit.letters (run_id, version, body, status, author, note) VALUES (%s, %s, %s, %s, %s, %s)",
                     (run_id, v, text, status, author, note or None))
    return {"version": v, "status": status}


# ---------------------------------------------------------------- evidence pack and downloads

def _pack(run_id: UUID) -> Path:
    _completed(run_id)
    return Path(build_pack(run_id))


@app.get("/api/runs/{run_id}/index")
def pack_index(run_id: UUID) -> dict:
    return {"markdown": (_pack(run_id) / "index.md").read_text(encoding="utf-8")}


@app.get("/api/runs/{run_id}/files/{name}")
def pack_file(run_id: UUID, name: str) -> FileResponse:
    if name not in _PACK_FILES:
        raise HTTPException(404)
    return FileResponse(_pack(run_id) / name, media_type=_PACK_FILES[name], filename=f"{name.rsplit('.', 1)[0]}_{str(run_id)[:8]}.{name.rsplit('.', 1)[1]}")


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

    _completed(run_id)
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


# ---------------------------------------------------------------- source records and advanced query

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
