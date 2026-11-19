"""Web platform for collections auditors: take in an audit request, confirm how its questions were read, run the evidence tests,
review every finding with its cited records, follow up what could not be determined, and release a cited response letter and
evidence pack.

  python -m agent serve            then open http://127.0.0.1:8000

Set APP_PASSWORD to require a password (any user name) before anything is served. The areas live in agent/web/routers/, shared
helpers in agent/web/common.py. Findings come from audit.* and are never changed (docs/decisions.md D-005); runs go through
agent.services, the only writer of findings."""
from __future__ import annotations

import base64
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from agent.web.common import STATIC
from agent.web.routers import accounts, agent, intake, knowledge, letter, pack, records, reference, runs

app = FastAPI(title="Audit evidence platform")

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



app.include_router(reference.router)
app.include_router(intake.router)
app.include_router(runs.router)
app.include_router(accounts.router)
app.include_router(letter.router)
app.include_router(pack.router)
app.include_router(knowledge.router)
app.include_router(records.router)
app.include_router(agent.router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
