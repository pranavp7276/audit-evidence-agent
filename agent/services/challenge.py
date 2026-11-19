"""Run the skeptic over a run's gaps and keep what it says. Challenges are stored beside the findings and never change them."""
from __future__ import annotations

import os
from uuid import UUID

from agent.checks.catalog import CHECK_INFO
from agent.core import llm
from agent.core.db import connect
from agent.core.trace import Trace
from agent.runtime.skeptic import challenge_many, challenge_one

DEFAULT_LIMIT = 40


def _items(run_id: UUID, finding_ids: list[int] | None = None, limit: int = DEFAULT_LIMIT) -> tuple[list[dict], int]:
    """Gaps with their cited records, ready for the skeptic. With no ids, a spread across the checks (every check is represented)."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT f.finding_id, f.check_id, f.reason, c.check_type FROM audit.findings f JOIN audit.checks c USING (run_id, check_id)
               WHERE f.run_id = %s AND f.status = 'gap' ORDER BY f.check_id, f.finding_id""", (run_id,)).fetchall()
        total = len(rows)
        if finding_ids is not None:
            rows = [r for r in rows if r["finding_id"] in set(finding_ids)]
        elif len(rows) > limit:  # evenly spaced within each check, so no check is skipped and no region of the run is
            by_check: dict[str, list[dict]] = {}
            for r in rows:
                by_check.setdefault(r["check_id"], []).append(r)
            per = max(1, limit // len(by_check))
            rows = [g[int(i * len(g) / min(per, len(g)))] for g in by_check.values() for i in range(min(per, len(g)))]
        cites: dict[int, list[dict]] = {}
        for c in conn.execute("SELECT finding_id, source_table, record_key, record_ts_utc, role, extract FROM audit.citations WHERE finding_id = ANY(%s) ORDER BY citation_id",
                              ([r["finding_id"] for r in rows],)):
            cites.setdefault(c["finding_id"], []).append(c)
    info = CHECK_INFO
    return [{"finding_id": r["finding_id"], "reason": r["reason"], "citations": cites.get(r["finding_id"], []),
             "rule": f"{info[r['check_type']]['tests']} A gap is reported when: {info[r['check_type']]['gap']}"} for r in rows if r["check_type"] in info], total


def _save(run_id: UUID, results: list[dict], requested_by: str | None) -> None:
    if not results:
        return
    with connect() as conn, conn.transaction():
        conn.cursor().executemany(
            "INSERT INTO audit.finding_challenges (run_id, finding_id, verdict, concern, model, requested_by) VALUES (%s, %s, %s, %s, %s, %s)",
            [(run_id, r["finding_id"], r["verdict"], r["concern"], r["model"], requested_by) for r in results])


def challenge_run(run_id: UUID, trace: Trace | None = None) -> dict:
    """The automatic pass at the end of a run. Bounded (SKEPTIC_LIMIT gaps, default 40; 0 turns it off) and never fails the run."""
    limit = int(os.environ.get("SKEPTIC_LIMIT", DEFAULT_LIMIT))
    out = {"asked": 0, "supports": 0, "disputes": 0, "unclear": 0, "skipped": 0, "gaps": 0}
    if limit <= 0 or not llm.available():
        if trace:
            trace.step("challenge", "skeptic", "Second reading of the gaps was not run (no model available, or turned off).", status="info")
        return out
    items, out["gaps"] = _items(run_id, None, limit)
    results, out["skipped"] = challenge_many(items)
    _save(run_id, results, None)
    for r in results:
        out[r["verdict"]] += 1
    out["asked"] = len(results)
    if trace:
        trace.step("challenge", "skeptic",
                   f"A second model read {out['asked']} of {out['gaps']} gap(s) against the records each cites: {out['supports']} supported, {out['disputes']} disputed, "
                   f"{out['unclear']} unclear" + (f"; {out['skipped']} not reached" if out["skipped"] else "") + ". It changes no finding; disagreements go to the top of the review queue.",
                   status="unresolved" if out["disputes"] else "ok", detail=out)
    return out


def challenge_finding(run_id: UUID, finding_id: int, requested_by: str) -> dict:
    """A reviewer asks for a second reading of one gap."""
    items, _ = _items(run_id, [finding_id])
    if not items:
        raise ValueError("Only a reported gap in this audit can be challenged.")
    if not llm.available():
        raise ValueError("No model is available for a second reading.")
    result = challenge_one(items[0])
    _save(run_id, [result], requested_by)
    return result
