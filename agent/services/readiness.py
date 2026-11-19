"""Readiness: run the same audit before anyone asks, and say what an auditor's sample would find.

"Report every gap before the auditor finds it" cannot wait for the request. A readiness check is an ordinary audit of a random sample of recently
contacted accounts, started by us. Because the sample is random, the share of accounts with a gap in it estimates the share in the whole book, and
that gives a forecast for any sample an auditor might draw, with its uncertainty stated (a Wilson 95% interval).
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from uuid import UUID

from agent.core.contracts import Request
from agent.core.db import connect
from agent.services import store

DEFAULT_SIZE = 1000
AUDITOR_SAMPLE = 300  # what a typical audit request samples


def start(size: int, created_by: str | None) -> tuple[UUID, Request, dict]:
    """Create the readiness run. The caller runs it with services.audit.process, with the returned period and size."""
    today = date.today()
    period = {"start": (today - timedelta(days=365)).isoformat(), "end": (today + timedelta(days=1)).isoformat(), "label": "the last 12 months"}
    request = Request(request_id=f"READINESS-{today:%Y-%m-%d}", source="text",
                      text=f"Readiness check: a compliance audit of all guardrails on a random sample of {size} accounts contacted in {period['label']}.")
    return store.start_run(request, created_by=created_by, kind="readiness"), request, period


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def forecast(sample: int = AUDITOR_SAMPLE) -> dict | None:
    """From the latest finished readiness check: for each test, how many of `sample` accounts an auditor could expect to find with a gap."""
    with connect() as conn:
        run = conn.execute("SELECT run_id, request_id, started_at, finished_at FROM audit.runs WHERE kind = 'readiness' AND status = 'completed' "
                           "ORDER BY started_at DESC LIMIT 1").fetchone()
        if not run:
            return None
        rows = conn.execute(
            """SELECT c.check_type, count(DISTINCT f.account_id) AS tested,
                      count(DISTINCT f.account_id) FILTER (WHERE f.status = 'gap') AS with_gap
               FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) WHERE f.run_id = %s AND c.check_type <> 'other'
               GROUP BY c.check_type ORDER BY with_gap DESC""", (run["run_id"],)).fetchall()
    tests = []
    for r in rows:
        lo, hi = _wilson(r["with_gap"], r["tested"])
        tests.append({"check_type": r["check_type"], "tested": r["tested"], "with_gap": r["with_gap"], "expected": round(sample * r["with_gap"] / max(r["tested"], 1)),
                      "low": math.floor(sample * lo), "high": math.ceil(sample * hi)})
    return {"run_id": str(run["run_id"]), "request_id": run["request_id"], "finished_at": run["finished_at"], "sample": sample, "tests": tests}
