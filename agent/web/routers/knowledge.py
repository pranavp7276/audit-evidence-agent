"""Knowledge base and versioned guardrails."""

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from psycopg.types.json import Jsonb

from agent.db import connect
from agent.guardrails import SEVERITY_DEFAULT, split_clauses, suggest
from agent.parser.request_parser import read_request
from agent.web.common import _all, _one

router = APIRouter()


_GUARDRAIL_COLS = """g.guardrail_id, g.version, g.check_type, g.title, g.obligation, g.source_doc_id, g.source_clause, g.source_label,
                     g.applicability, g.parameters, g.required_evidence, g.default_severity, g.priority_weight, g.weight_reason,
                     g.effective_from, g.status, g.created_by, g.created_at, d.title AS source_doc_title,
                     (SELECT count(*) FROM audit.guardrail h WHERE h.guardrail_id = g.guardrail_id) AS versions"""
_LATEST = "(SELECT DISTINCT ON (guardrail_id) * FROM audit.guardrail ORDER BY guardrail_id, version DESC) g"


@router.get("/api/kb")
def kb_list() -> list[dict]:
    return _all("""SELECT d.doc_id, d.title, d.issuer, d.doc_type, d.reference_no, d.effective_date, d.uploaded_by, d.created_at,
                          (SELECT count(*) FROM audit.kb_clause c WHERE c.doc_id = d.doc_id) AS clauses,
                          (SELECT count(DISTINCT g.guardrail_id) FROM audit.guardrail g WHERE g.source_doc_id = d.doc_id) AS guardrails
                   FROM audit.kb_document d ORDER BY d.created_at DESC""")


@router.post("/api/kb")
async def kb_add(title: str = Form(...), doc_type: str = Form("circular"), issuer: str = Form(""), reference_no: str = Form(""),
                 effective_date: str = Form(""), text: str = Form(""), uploaded_by: str = Form(""), file: UploadFile | None = File(None)) -> dict:
    if doc_type not in ("circular", "policy", "sop"):
        raise HTTPException(400, "Type must be circular, policy or sop.")
    if not uploaded_by.strip():
        raise HTTPException(400, "Enter your name first.")
    if file is not None and file.filename:
        path = Path(tempfile.mkdtemp(prefix="kb-")) / Path(file.filename).name
        path.write_bytes(await file.read())
        try:
            text = read_request(path, "KB").text
        except Exception as exc:
            raise HTTPException(400, f"Could not read the file: {exc}")
    clauses = split_clauses(text)
    if not clauses:
        raise HTTPException(400, "The document has no text. Upload a text or PDF file, or paste the text.")
    try:
        eff = date.fromisoformat(effective_date) if effective_date else None
    except ValueError:
        raise HTTPException(400, "The effective date must look like 2026-04-01.")
    with connect() as conn, conn.transaction():
        doc_id = conn.execute("""INSERT INTO audit.kb_document (title, issuer, doc_type, reference_no, effective_date, body, uploaded_by)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING doc_id""",
                              (title.strip(), issuer.strip() or None, doc_type, reference_no.strip() or None, eff, text, uploaded_by.strip())).fetchone()["doc_id"]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO audit.kb_clause (doc_id, seq, clause_no, body) VALUES (%s, %s, %s, %s)",
                            [(doc_id, i, no, body) for i, (no, body) in enumerate(clauses, 1)])
    return {"doc_id": doc_id, "clauses": len(clauses)}


@router.get("/api/kb/{doc_id}")
def kb_get(doc_id: int) -> dict:
    doc = _one("SELECT doc_id, title, issuer, doc_type, reference_no, effective_date, uploaded_by, created_at FROM audit.kb_document WHERE doc_id = %s", (doc_id,))
    if not doc:
        raise HTTPException(404, "Document not found")
    clauses = _all("SELECT seq, clause_no, body FROM audit.kb_clause WHERE doc_id = %s ORDER BY seq", (doc_id,))
    guardrails = _all(f"SELECT {_GUARDRAIL_COLS} FROM {_LATEST} LEFT JOIN audit.kb_document d ON d.doc_id = g.source_doc_id "
                      "WHERE g.source_doc_id = %s ORDER BY g.guardrail_id", (doc_id,))
    return {"doc": doc, "clauses": clauses, "guardrails": guardrails}


@router.post("/api/kb/{doc_id}/suggest")
async def kb_suggest(doc_id: int, request: Request) -> dict:
    """Draft guardrails from the document's clauses (keyword-based). Nothing is published; Compliance reviews each."""
    body = await request.json()
    by = str(body.get("by", "")).strip()
    if not by:
        raise HTTPException(400, "Enter your name first.")
    doc = _one("SELECT doc_id, effective_date FROM audit.kb_document WHERE doc_id = %s", (doc_id,))
    if not doc:
        raise HTTPException(404, "Document not found")
    clauses = [(c["clause_no"], c["body"]) for c in _all("SELECT clause_no, body FROM audit.kb_clause WHERE doc_id = %s ORDER BY seq", (doc_id,))]
    have = {(g["source_clause"], g["check_type"]) for g in _all("SELECT source_clause, check_type FROM audit.guardrail WHERE source_doc_id = %s", (doc_id,))}
    made = 0
    with connect() as conn, conn.transaction():
        for s in suggest(clauses):
            if (s["source_clause"], s["check_type"]) in have:
                continue
            gid = conn.execute("SELECT nextval('audit.guardrail_id_seq') AS i").fetchone()["i"]
            conn.execute("""INSERT INTO audit.guardrail (guardrail_id, version, check_type, title, obligation, source_doc_id, source_clause, parameters,
                                                         default_severity, effective_from, status, created_by)
                            VALUES (%s, 1, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s)""",
                         (gid, s["check_type"], s["title"], s["obligation"], doc_id, s["source_clause"], Jsonb(s["parameters"]), s["default_severity"],
                          doc["effective_date"] or date.today(), by))
            made += 1
    return {"created": made}


@router.get("/api/guardrails")
def guardrails_list() -> list[dict]:
    return _all(f"SELECT {_GUARDRAIL_COLS} FROM {_LATEST} LEFT JOIN audit.kb_document d ON d.doc_id = g.source_doc_id "
                "ORDER BY (g.status = 'published') DESC, g.check_type, g.guardrail_id")


@router.get("/api/guardrails/{gid}/versions")
def guardrail_versions(gid: int) -> list[dict]:
    return _all(f"SELECT {_GUARDRAIL_COLS} FROM audit.guardrail g LEFT JOIN audit.kb_document d ON d.doc_id = g.source_doc_id "
                "WHERE g.guardrail_id = %s ORDER BY g.version DESC", (gid,))


def _guardrail_fields(b: dict) -> dict:
    ct, sev = b.get("check_type"), str(b.get("default_severity", "")).strip()
    if ct not in SEVERITY_DEFAULT:
        raise HTTPException(400, "Choose which control this guardrail tests.")
    if not str(b.get("title", "")).strip() or not str(b.get("obligation", "")).strip():
        raise HTTPException(400, "A guardrail needs a title and the obligation it tests.")
    if not sev:
        raise HTTPException(400, "Set the default severity.")
    try:
        weight = int(b.get("priority_weight", 1))
        eff = date.fromisoformat(str(b.get("effective_from")))
    except (TypeError, ValueError):
        raise HTTPException(400, "Weight must be 1, 2 or 3 and the effective date must look like 2026-04-01.")
    if weight not in (1, 2, 3):
        raise HTTPException(400, "Weight must be 1, 2 or 3.")
    reason = str(b.get("weight_reason", "")).strip()
    if weight != 1 and not reason:
        raise HTTPException(400, "Give the reason for a weight above 1; it is recorded with the guardrail.")
    if b.get("status") not in ("draft", "published", "retired"):
        raise HTTPException(400, "Status must be draft, published or retired.")
    if not str(b.get("created_by", "")).strip():
        raise HTTPException(400, "Enter your name first.")
    return {"check_type": ct, "title": str(b["title"]).strip(), "obligation": str(b["obligation"]).strip(), "source_doc_id": b.get("source_doc_id") or None,
            "source_clause": (b.get("source_clause") or None), "source_label": (b.get("source_label") or None), "applicability": Jsonb(b.get("applicability") or {}),
            "parameters": Jsonb(b.get("parameters") or {}), "required_evidence": (b.get("required_evidence") or None), "default_severity": sev,
            "priority_weight": weight, "weight_reason": reason or None, "effective_from": eff, "status": b["status"], "created_by": str(b["created_by"]).strip()}


async def _save_guardrail(gid: int | None, request: Request) -> dict:
    f = _guardrail_fields(await request.json())
    with connect() as conn, conn.transaction():
        if gid is None:
            gid = conn.execute("SELECT nextval('audit.guardrail_id_seq') AS i").fetchone()["i"]
            version = 1
        else:
            row = conn.execute("SELECT max(version) AS v FROM audit.guardrail WHERE guardrail_id = %s", (gid,)).fetchone()
            if row["v"] is None:
                raise HTTPException(404, "Guardrail not found")
            version = row["v"] + 1
        conn.execute("""INSERT INTO audit.guardrail (guardrail_id, version, check_type, title, obligation, source_doc_id, source_clause, source_label,
                            applicability, parameters, required_evidence, default_severity, priority_weight, weight_reason, effective_from, status, created_by)
                        VALUES (%(gid)s, %(version)s, %(check_type)s, %(title)s, %(obligation)s, %(source_doc_id)s, %(source_clause)s, %(source_label)s,
                            %(applicability)s, %(parameters)s, %(required_evidence)s, %(default_severity)s, %(priority_weight)s, %(weight_reason)s,
                            %(effective_from)s, %(status)s, %(created_by)s)""", {**f, "gid": gid, "version": version})
    return {"guardrail_id": gid, "version": version}


@router.post("/api/guardrails")
async def guardrail_create(request: Request) -> dict:
    return await _save_guardrail(None, request)


@router.post("/api/guardrails/{gid}/versions")
async def guardrail_new_version(gid: int, request: Request) -> dict:
    """A change is a new version; earlier versions stay, and audits keep the version they applied."""
    return await _save_guardrail(gid, request)


