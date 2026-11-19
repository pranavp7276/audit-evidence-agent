"""The audit plan: which audits and readiness checks are expected, who owns them, and when they are due (the multi-year view is the plan by month)."""
from __future__ import annotations

from datetime import date
from uuid import UUID

from agent.core.db import connect

STATUSES = ("planned", "in_progress", "done", "cancelled")
RECURRENCE = {"monthly": 1, "quarterly": 3, "yearly": 12}


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, min(d.day, 28))


def create(title: str, lender: str | None, scope: str | None, kind: str, planned_start: date | None, due: date | None, owner: str | None, recurrence: str, actor: str) -> int:
    if not title.strip():
        raise ValueError("Give the planned audit a title.")
    if kind not in ("audit", "readiness"):
        raise ValueError("A plan entry is an audit or a readiness check.")
    if recurrence != "none" and recurrence not in RECURRENCE:
        raise ValueError("Unknown recurrence.")
    if planned_start and due and due < planned_start:
        raise ValueError("The due date is before the start date.")
    with connect() as conn:
        return conn.execute(
            """INSERT INTO audit.audit_plan (title, lender, scope, kind, planned_start, due_date, owner, recurrence, created_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING plan_id""",
            (title.strip(), lender or None, scope or None, kind, planned_start, due, owner or None, recurrence, actor)).fetchone()["plan_id"]


def set_status(plan_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError("Unknown status.")
    with connect() as conn:
        if not conn.execute("UPDATE audit.audit_plan SET status = %s WHERE plan_id = %s RETURNING plan_id", (status, plan_id)).fetchone():
            raise LookupError("No such plan entry.")


def link_run(plan_id: int, run_id: UUID) -> None:
    """The audit for this plan entry was started. A recurring entry schedules the next one."""
    with connect() as conn, conn.transaction():
        row = conn.execute("UPDATE audit.audit_plan SET run_id = %s, status = 'in_progress' WHERE plan_id = %s AND run_id IS NULL RETURNING *", (run_id, plan_id)).fetchone()
        if row and row["recurrence"] in RECURRENCE and (row["planned_start"] or row["due_date"]):
            step = RECURRENCE[row["recurrence"]]
            conn.execute(
                """INSERT INTO audit.audit_plan (title, lender, scope, kind, planned_start, due_date, owner, recurrence, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (row["title"], row["lender"], row["scope"], row["kind"], _add_months(row["planned_start"], step) if row["planned_start"] else None,
                 _add_months(row["due_date"], step) if row["due_date"] else None, row["owner"], row["recurrence"], row["created_by"]))
