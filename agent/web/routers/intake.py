"""Intake: read a request, show how its questions were interpreted, then start the run."""

import json
import re
import tempfile
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agent.core.contracts import CheckSpec, CheckType
from agent.core.contracts import Request as AuditRequest
from agent.intake.request_parser import _SOURCES, parse_checks_with_info, parse_sample, read_request
from agent.intake.sampling import MAX_SAMPLE, contacted_accounts, resolve_references
from agent.services import plan, store
from agent.services.audit import process
from agent.web.common import _RUN_LOCK, ROOT

router = APIRouter()


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


@router.post("/api/requests/preview")
async def preview(request_id: str = Form("PREVIEW"), text: str = Form(""), source: str = Form("text"),
                  file: UploadFile | None = File(None)) -> dict:
    """Read the request and show how it would be tested, without running anything."""
    request = await _request_from_form(request_id.strip() or "PREVIEW", text, source, file)
    try:
        checks, scale, info = parse_checks_with_info(request)
    except Exception as exc:
        raise HTTPException(400, f"Could not interpret the request: {exc}")
    stated = parse_sample(request.text)
    accounts = stated["accounts"]
    refs = resolve_references(accounts)
    unmatched = [r["ref"] for r in refs if r["status"] == "unmatched"]
    ambiguous = [{"ref": r["ref"], "note": r["note"]} for r in refs if r["status"] == "ambiguous"]
    rows = [{"check_id": c.check_id, "question_ref": c.question_ref, "question_text": c.question_text,
             "check_type": c.check_type.value, "severity": c.test.get("severity"), "sources": [s.value for s in c.sources],
             "reader": c.test.get("reader"), "confidence": c.test.get("confidence"), "triage": c.test.get("triage")}
            for c in checks]
    period = stated["period"]
    return {"source": request.source, "text": request.text, "checks": rows, "scale": scale, "accounts": len(accounts),
            "matched": sum(r["status"] == "matched" for r in refs), "unmatched": unmatched[:100], "ambiguous": ambiguous[:100],
            "parser": info["reader"], "models": info["models"], "parser_note": info["note"],
            "instruction": not re.search(r"^\s*Q\d+\s*[.:)]", request.text, re.MULTILINE),
            "period": period, "size": stated["size"], "eligible": contacted_accounts(period), "max_sample": MAX_SAMPLE}


@router.get("/api/population")
def population(start: str = "", end: str = "") -> dict:
    """How many accounts had a contact in a period (India calendar days, end exclusive)."""
    try:
        period = {"start": start, "end": end, "label": ""} if start and end else None
        return {"eligible": contacted_accounts(period)}
    except ValueError:
        raise HTTPException(400, "Dates must look like 2026-10-01.")


@router.post("/api/runs")
async def create_run(request_id: str = Form(...), text: str = Form(""), source: str = Form("text"), lender: str = Form(""),
                     response_due: str = Form(""), created_by: str = Form(""), accounts: str = Form(""),
                     random_n: int | None = Form(None), checks: str = Form(""), scale: str = Form(""),
                     period_start: str = Form(""), period_end: str = Form(""), period_label: str = Form(""),
                     sample_size: int | None = Form(None), plan_id: int | None = Form(None), file: UploadFile | None = File(None)) -> dict:
    request_id = request_id.strip()
    if not request_id:
        raise HTTPException(400, "Give the request an id, e.g. CO-04.")
    request = await _request_from_form(request_id, text, source, file)
    specs = None
    if checks.strip():  # the auditor's reviewed interpretation
        try:
            specs = [CheckSpec(check_id=c["check_id"], question_ref=c["question_ref"], question_text=c["question_text"],
                               check_type=CheckType(c["check_type"]), sample={}, sources=_SOURCES[CheckType(c["check_type"])],
                               test={**({"severity": c["severity"]} if c.get("severity") else {}),
                                     **({"reader": c["reader"], "confidence": c.get("confidence")} if c.get("reader") else {})}) for c in json.loads(checks)]
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
    if plan_id:  # the audit was started from the audit plan: link it, and schedule the next one if the entry recurs
        plan.link_run(plan_id, run_id)

    def work() -> None:
        with _RUN_LOCK:
            try:
                process(run_id, request, accounts=sample, random_n=random_n, log=lambda _: None, checks=specs, scale=labels,
                        period=period, size=sample_size)
            except Exception:
                pass  # recorded on the run (status failed + notes); the page shows it

    threading.Thread(target=work, daemon=True).start()
    return {"run_id": str(run_id)}


