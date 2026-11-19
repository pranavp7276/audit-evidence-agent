"""Issues: confirmed gaps that are being tracked to closure. An issue points at findings and never changes them.

Fixing a gap is outside this platform (docs/problem.md); an issue records who owns it, when it is due and where it stands, and what evidence closed it.
Every change adds an event; events are never edited.
"""
from __future__ import annotations

from datetime import date

from agent.core.db import connect

STATUSES = ("open", "in_progress", "resolved", "verified", "wont_fix")
CLOSED = ("verified", "wont_fix")
# resolved means the owner says it is fixed; only a second person verifying closes it
TRANSITIONS = {"open": ("in_progress", "resolved", "wont_fix"), "in_progress": ("open", "resolved", "wont_fix"), "resolved": ("in_progress", "verified"),
               "verified": (), "wont_fix": ("open",)}


def create(finding_ids: list[int], title: str, owner: str | None, due: date | None, description: str | None, actor: str) -> int:
    """Open an issue for a set of findings. Only reported gaps can be raised, and a gap already in an open issue is refused, so nothing is tracked twice."""
    if not title.strip():
        raise ValueError("Give the issue a title.")
    if not finding_ids:
        raise ValueError("Choose at least one gap.")
    with connect() as conn, conn.transaction():
        rows = conn.execute("SELECT f.finding_id, f.severity, c.check_type FROM audit.findings f JOIN audit.checks c USING (run_id, check_id) "
                            "WHERE f.finding_id = ANY(%s) AND f.status = 'gap'", (finding_ids,)).fetchall()
        if len(rows) != len(set(finding_ids)):
            raise ValueError("Only reported gaps can be raised as issues.")
        taken = conn.execute("SELECT DISTINCT i.issue_id FROM audit.issue_findings l JOIN audit.issues i USING (issue_id) "
                             "WHERE l.finding_id = ANY(%s) AND i.status NOT IN ('verified', 'wont_fix')", (finding_ids,)).fetchall()
        if taken:
            raise ValueError(f"Some of these gaps are already in open issue #{taken[0]['issue_id']}.")
        types = {r["check_type"] for r in rows}
        issue_id = conn.execute(
            "INSERT INTO audit.issues (title, description, check_type, severity, owner, due_date, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING issue_id",
            (title.strip(), description or None, types.pop() if len(types) == 1 else None, rows[0]["severity"], owner or None, due, actor)).fetchone()["issue_id"]
        conn.cursor().executemany("INSERT INTO audit.issue_findings (issue_id, finding_id) VALUES (%s, %s)", [(issue_id, r["finding_id"]) for r in rows])
        conn.execute("INSERT INTO audit.issue_events (issue_id, actor, kind, body) VALUES (%s, %s, 'created', %s)", (issue_id, actor, f"Raised for {len(rows)} gap(s)."))
    return issue_id


def update(issue_id: int, actor: str, status: str | None = None, owner: str | None = None, due: date | None = None, note: str | None = None) -> None:
    """Change an issue's status, owner or due date, or add a note. Each change is an event."""
    with connect() as conn, conn.transaction():
        cur = conn.execute("SELECT status FROM audit.issues WHERE issue_id = %s FOR UPDATE", (issue_id,)).fetchone()
        if not cur:
            raise LookupError("No such issue.")
        if status and status != cur["status"]:
            if status not in TRANSITIONS[cur["status"]]:
                raise ValueError(f"An issue that is {cur['status'].replace('_', ' ')} cannot go straight to {status.replace('_', ' ')}.")
            if status == "verified":  # the person who says it is fixed is not the person who verifies it
                resolver = conn.execute("SELECT actor FROM audit.issue_events WHERE issue_id = %s AND kind = 'status' AND body = 'resolved' ORDER BY event_id DESC LIMIT 1", (issue_id,)).fetchone()
                if resolver and resolver["actor"].strip().lower() == actor.strip().lower():
                    raise ValueError("A different person has to verify that the issue is resolved.")
            if status in ("resolved", "wont_fix") and not (note or "").strip():
                raise ValueError("Say how it was resolved, or why it will not be fixed.")
            conn.execute("UPDATE audit.issues SET status = %s WHERE issue_id = %s", (status, issue_id))
            conn.execute("INSERT INTO audit.issue_events (issue_id, actor, kind, body) VALUES (%s, %s, 'status', %s)", (issue_id, actor, status))
        if owner is not None:
            conn.execute("UPDATE audit.issues SET owner = %s WHERE issue_id = %s", (owner or None, issue_id))
            conn.execute("INSERT INTO audit.issue_events (issue_id, actor, kind, body) VALUES (%s, %s, 'owner', %s)", (issue_id, actor, owner or "(none)"))
        if due is not None:
            conn.execute("UPDATE audit.issues SET due_date = %s WHERE issue_id = %s", (due, issue_id))
            conn.execute("INSERT INTO audit.issue_events (issue_id, actor, kind, body) VALUES (%s, %s, 'due', %s)", (issue_id, actor, due.isoformat()))
        if note and note.strip():
            conn.execute("INSERT INTO audit.issue_events (issue_id, actor, kind, body) VALUES (%s, %s, 'note', %s)", (issue_id, actor, note.strip()))
