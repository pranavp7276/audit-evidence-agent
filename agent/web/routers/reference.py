"""Configuration, the assistant and reference data (rules, sources, examples)."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.checks.catalog import ASSUMPTIONS, CHECK_INFO, SOURCES, STATUS_MEANING
from agent.core import llm
from agent.core.db import read_rows
from agent.services.pack import DISPOSITIONS
from agent.web.common import EXAMPLES, GAP_KEYS

router = APIRouter()


@router.get("/api/config")
def config() -> dict:
    on = llm.available()
    return {"parser": "llm" if on else "keyword", "models": llm.models() if on else None,
            "password_protected": bool(os.environ.get("APP_PASSWORD")), "sla_minutes": 120,
            "check_types": {k: v["title"] for k, v in CHECK_INFO.items()}}


class _Ask(BaseModel):
    question: str
    context: str = ""


@router.post("/api/assist")
def assist(body: _Ask) -> dict:
    """The help assistant (conversational model), answering only from the guide text the page sends. It never sees audit data."""
    q = body.question.strip()
    if not q:
        raise HTTPException(400, "Ask a question first.")
    if not llm.available():
        raise HTTPException(503, "The assistant needs a model key (SARVAM_API_KEY). The Guide pages cover the same ground.")
    system = ("You are the help assistant inside an audit evidence platform for collections compliance. Answer ONLY from the guide text below, "
              "in plain, short steps for a compliance reviewer, auditor or team member. If the guide does not cover it, say so and point to the "
              "most relevant guide topic. Never invent features, numbers or data, and never answer questions about specific borrowers or accounts.\n\n"
              "GUIDE:\n" + body.context[:9000])
    try:
        return {"answer": llm.chat([{"role": "system", "content": system}, {"role": "user", "content": q[:1000]}]), "model": llm.models()["chat"]}
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))


@router.get("/api/rules")
def rules() -> dict:
    policy = read_rows("SELECT rule_key, rule_value, unit, counting_unit, counting_rule, effective_from, effective_to, note, institution_code "
                       "FROM staging.policy_rules ORDER BY rule_key, effective_from")
    return {"checks": CHECK_INFO, "status_meaning": STATUS_MEANING, "dispositions": DISPOSITIONS,
            "assumptions": [{"topic": k, "text": v} for k, v in ASSUMPTIONS], "policy": policy}


@router.get("/api/data-sources")
def data_sources() -> list[dict]:
    out = []
    for label, view, col, tz in SOURCES:
        sel = f"count(*) AS n, min({col}) AS first, max({col}) AS last" if col else "count(*) AS n, NULL AS first, NULL AS last"
        row = read_rows(f"SELECT {sel} FROM {view}")[0]
        out.append({"source": label, "view": view, "rows": row["n"], "first": row["first"], "last": row["last"], "timezone": tz})
    return out


@router.get("/api/examples")
def examples() -> list[str]:
    return sorted(p.name for p in EXAMPLES.glob("*") if p.is_file() and p.name != ".gitkeep")


@router.get("/api/examples/{name}")
def example(name: str) -> dict:
    path = EXAMPLES / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return {"name": path.name, "text": path.read_text(encoding="utf-8")}


@router.get("/api/gap-keys")
def gap_keys() -> list[str]:
    return sorted(p.name for p in GAP_KEYS.glob("*.csv"))


