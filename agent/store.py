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


def start_run(request: Request, lender: str | None = None, response_due: str | None = None,
              created_by: str | None = None) -> UUID:
    with connect() as conn:
        row = conn.execute(
            """INSERT INTO audit.runs (request_id, request_source, request_path, severity_scale, agent_version,
                                       lender, response_due, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING run_id""",
            (request.request_id, request.source, request.path,
             Jsonb(request.severity_scale), _git_sha(), lender or None, response_due or None, created_by or None),
        ).fetchone()
        return row["run_id"]


def set_severity_scale(run_id: UUID, scale: list[str]) -> None:
    """Record the request's severity scale once the parser has read it."""
    with connect() as conn:
        conn.execute("UPDATE audit.runs SET severity_scale = %s WHERE run_id = %s", (Jsonb(scale), run_id))


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


def save_sample_references(run_id: UUID, refs: list[dict]) -> None:
    """Record every account reference from the request, as written, and how it matched a CN account."""
    if not refs:
        return
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO audit.sample_references (run_id, original_ref, match_status, matched_account_id, candidates, note)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
            [(run_id, r["ref"], r["status"], r["account_id"], r["candidates"], r["note"]) for r in refs])


def save_findings(run_id: UUID, findings: list[Finding]) -> None:
    """Insert findings with their citations in one transaction.

    The database re-checks the guardrails at commit: if any evidenced/gap finding lacks a
    citation, the whole batch is rejected rather than partially saved.
    """
    if not findings:
        return
    with connect() as conn, conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO audit.findings (run_id, check_id, account_id, subject_ref, status,
                                           severity, reason, evidence_query)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING finding_id""",
            [(run_id, f.check_id, f.account_id, f.subject_ref, f.status.value,
              f.severity, f.reason, f.evidence_query) for f in findings],
            returning=True)
        ids = []
        while True:
            ids.append(cur.fetchone()["finding_id"])
            if not cur.nextset():
                break
        citations = [
            (fid, c.source_system.value, c.source_table, c.record_key, c.record_ts_utc, c.record_ts_original,
             Jsonb(c.extract) if c.extract is not None else None, c.role)
            for fid, f in zip(ids, findings) for c in f.citations]
        cur.executemany(
            """INSERT INTO audit.citations (finding_id, source_system, source_table, record_key,
                                            record_ts_utc, record_ts_original, extract, role)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", citations)


def finish_run(run_id: UUID, status: str = "completed", notes: str | None = None) -> None:
    """Mark a run done. After 'completed', its findings are frozen by a database trigger."""
    with connect() as conn:
        conn.execute(
            "UPDATE audit.runs SET status = %s, finished_at = now(), notes = %s WHERE run_id = %s",
            (status, notes, run_id),
        )


__all__ = ["start_run", "set_severity_scale", "save_sample_references", "save_checks", "save_findings", "finish_run"]
