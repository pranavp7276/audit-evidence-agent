"""Writes agent output into the audit schema. The only module that writes to the database."""
from __future__ import annotations

import subprocess
from uuid import UUID

from psycopg.types.json import Jsonb

from agent.contracts import CheckSpec, Finding, Request
from agent.db import connect


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def start_run(request: Request) -> UUID:
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO audit.runs (request_id, request_source, request_path, severity_scale, agent_version)
               VALUES (%s, %s, %s, %s, %s) RETURNING run_id""",
            (request.request_id, request.source, request.path,
             Jsonb(request.severity_scale), _git_sha()),
        ).fetchone()
        return row["run_id"]


def save_checks(run_id: UUID, checks: list[CheckSpec], samples: dict[str, list[str]]) -> None:
    """Persist parsed checks and the accounts sampled for each."""
    with connect() as conn, conn.transaction():
        for c in checks:
            conn.execute(
                """INSERT INTO audit.checks (run_id, check_id, question_ref, question_text, check_type,
                                             sample_definition, test_definition, sources)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, c.check_id, c.question_ref, c.question_text, c.check_type.value,
                 Jsonb(c.sample), Jsonb(c.test), [s.value for s in c.sources]),
            )
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO audit.sample_accounts (run_id, check_id, account_id) VALUES (%s, %s, %s)",
                    [(run_id, c.check_id, a) for a in samples.get(c.check_id, [])],
                )


def save_findings(run_id: UUID, findings: list[Finding]) -> None:
    """Insert findings with their citations in one transaction.

    The database re-checks the guardrails at commit: if any evidenced/gap finding lacks a
    citation, the whole batch is rejected rather than partially saved.
    """
    with connect() as conn, conn.transaction():
        for f in findings:
            fid = conn.execute(
                """INSERT INTO audit.findings (run_id, check_id, account_id, subject_ref, status,
                                               severity, reason, evidence_query)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING finding_id""",
                (run_id, f.check_id, f.account_id, f.subject_ref, f.status.value,
                 f.severity, f.reason, f.evidence_query),
            ).fetchone()["finding_id"]
            for c in f.citations:
                conn.execute(
                    """INSERT INTO audit.citations (finding_id, source_system, source_table, record_key,
                                                    record_ts_utc, record_ts_original, extract, role)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (fid, c.source_system.value, c.source_table, c.record_key, c.record_ts_utc,
                     c.record_ts_original, Jsonb(c.extract) if c.extract is not None else None, c.role),
                )


def finish_run(run_id: UUID, status: str = "completed", notes: str | None = None) -> None:
    """Mark a run done. After 'completed', its findings are frozen by a database trigger."""
    with connect() as conn:
        conn.execute(
            "UPDATE audit.runs SET status = %s, finished_at = now(), notes = %s WHERE run_id = %s",
            (status, notes, run_id),
        )


__all__ = ["start_run", "save_checks", "save_findings", "finish_run"]
