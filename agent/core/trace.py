"""The agent's activity log for one run: plan, retrievals, evaluations, investigations. Saved to audit.agent_steps.

Tool calls are aggregated per check and tool (calls, rows, errors, time) rather than logged one by one, so a 300-account run
leaves a readable trace of a few hundred steps, not tens of thousands. A failure or an investigation is always its own step.
"""
from __future__ import annotations

import time
from collections import defaultdict
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from agent.core.db import connect, database_url


class Trace:
    """live=True writes each step to the database as it happens, so a person can watch the agent work; otherwise steps are written by save()."""

    def __init__(self, run_id: UUID | None = None, live: bool = False):
        self.run_id = run_id
        self.live = live and run_id is not None
        self._conn: psycopg.Connection | None = None
        self._written = 0
        self.steps: list[dict] = []
        self._stats: dict[tuple[str | None, str], dict] = defaultdict(lambda: {"calls": 0, "rows": 0, "errors": 0, "ms": 0.0, "error_kinds": set()})
        self._t0 = time.perf_counter()

    def step(self, phase: str, agent: str, action: str, *, tool: str | None = None, check_id: str | None = None, account_id: str | None = None,
             status: str = "ok", detail: dict | None = None, ms: float | None = None) -> dict:
        row = {"seq": len(self.steps) + 1, "phase": phase, "agent": agent, "action": action, "tool": tool, "check_id": check_id, "account_id": account_id,
               "status": status, "detail": detail or {}, "duration_ms": None if ms is None else int(ms)}
        self.steps.append(row)
        if self.live:
            self._write_pending()
        return row

    def _write_pending(self) -> None:
        """Write the steps not yet saved on one kept-open connection. A failure here must not stop the audit: save() writes whatever is left."""
        try:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(database_url(), autocommit=True)
            for s in self.steps[self._written:]:
                self._conn.execute(
                    """INSERT INTO audit.agent_steps (run_id, seq, phase, agent, action, tool, check_id, account_id, status, detail, duration_ms)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (self.run_id, s["seq"], s["phase"], s["agent"], s["action"], s["tool"], s["check_id"], s["account_id"], s["status"], Jsonb(s["detail"]), s["duration_ms"]))
                self._written += 1
        except Exception:
            self._conn = None

    def tool_call(self, check_id: str | None, tool: str, rows: int, ms: float, error: str | None = None) -> None:
        s = self._stats[(check_id, tool)]
        s["calls"] += 1
        s["rows"] += rows
        s["ms"] += ms
        if error:
            s["errors"] += 1
            s["error_kinds"].add(error)

    def flush_tool_stats(self, check_id: str | None) -> None:
        """One 'retrieve' step per tool the check used: what was asked for, how much came back, and whether anything failed."""
        for (cid, tool), s in sorted(self._stats.items(), key=lambda kv: kv[0][1]):
            if cid != check_id:
                continue
            self.step("retrieve", "retriever", f"Called {tool}: {s['calls']:,} request(s), {s['rows']:,} record(s) returned"
                      + (f", {s['errors']} failed" if s["errors"] else ""), tool=tool, check_id=cid, status="failed" if s["errors"] else "ok",
                      detail={"calls": s["calls"], "rows": s["rows"], "errors": s["errors"], "error_kinds": sorted(s["error_kinds"])}, ms=s["ms"])
        for key in [k for k in self._stats if k[0] == check_id]:
            del self._stats[key]

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)

    def save(self) -> None:
        if not self.run_id or not self.steps:
            return
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
        pending = self.steps[self._written:]
        if not pending:
            return
        with connect() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO audit.agent_steps (run_id, seq, phase, agent, action, tool, check_id, account_id, status, detail, duration_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                [(self.run_id, s["seq"], s["phase"], s["agent"], s["action"], s["tool"], s["check_id"], s["account_id"], s["status"],
                  Jsonb(s["detail"]), s["duration_ms"]) for s in pending])
