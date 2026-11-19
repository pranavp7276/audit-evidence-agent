"""The draft response letter, versioned."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from agent.core.db import connect
from agent.services.letter_lint import lint
from agent.services.pack import generate_letter
from agent.web.common import _all, _completed, _one

router = APIRouter()


@router.get("/api/runs/{run_id}/letter")
def letter(run_id: UUID) -> dict:
    _completed(run_id)
    versions = _all("SELECT version, status, author, note, created_at FROM audit.letters WHERE run_id = %s ORDER BY version DESC", (run_id,))
    latest = _one("SELECT * FROM audit.letters WHERE run_id = %s ORDER BY version DESC LIMIT 1", (run_id,))
    if latest:
        return {"body": latest["body"], "status": latest["status"], "version": latest["version"], "author": latest["author"],
                "created_at": latest["created_at"], "saved": True, "versions": versions}
    return {"body": generate_letter(run_id), "status": "draft", "version": 0, "author": None, "created_at": None, "saved": False, "versions": []}


@router.get("/api/runs/{run_id}/letter/version/{version}")
def letter_version(run_id: UUID, version: int) -> dict:
    row = _one("SELECT * FROM audit.letters WHERE run_id = %s AND version = %s", (run_id, version))
    if not row:
        raise HTTPException(404, "No such version")
    return row


@router.get("/api/runs/{run_id}/letter/generate")
def letter_generate(run_id: UUID) -> dict:
    _completed(run_id)
    return {"body": generate_letter(run_id)}


@router.post("/api/runs/{run_id}/letter")
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
    if status == "approved":
        problems = lint(run_id, text)
        if problems:
            raise HTTPException(400, f"The letter makes {len(problems)} statement(s) its findings do not support, for example line {problems[0]['line']}: "
                                     f"{problems[0]['problem']} Fix them on the Response letter tab before approving.")
    with connect() as conn, conn.transaction():
        v = conn.execute("SELECT COALESCE(max(version), 0) + 1 AS v FROM audit.letters WHERE run_id = %s", (run_id,)).fetchone()["v"]
        conn.execute("INSERT INTO audit.letters (run_id, version, body, status, author, note) VALUES (%s, %s, %s, %s, %s, %s)",
                     (run_id, v, text, status, author, note or None))
    return {"version": v, "status": status}




@router.post("/api/runs/{run_id}/letter/check")
async def check_letter(run_id: UUID, request: Request) -> dict:
    """Check the letter as written: every statement of fact must point at a finding or check, and its numbers must match the findings."""
    _completed(run_id)
    body = await request.json()
    problems = lint(run_id, str(body.get("body", "")))
    return {"ok": not problems, "problems": problems}
