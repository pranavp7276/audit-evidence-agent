"""Score a run against an answer key and keep the result, so the acceptance criteria can be shown next to the audit."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from agent.core.db import connect

KEYS = Path(__file__).resolve().parents[2] / "eval" / "gap_keys"


def find_key(request_id: str) -> Path | None:
    """The gap key named for this request (CN-01.csv for CN-01 or CN-01-rerun), longest name first. None when no key exists."""
    stems = sorted((p for p in KEYS.glob("*.csv") if "cannot_determine" not in p.stem), key=lambda p: -len(p.stem))
    return next((p for p in stems if request_id.upper().startswith(p.stem.upper())), None)


def score_and_save(run_id: UUID, key_path: Path, account_col: str = "account_id", check_col: str = "question_ref", scored_by: str | None = None) -> dict:
    from eval.score import (  # the scorer lives beside the answer keys
        load_gap_key,
        load_reported,
        score,
    )

    truth = load_gap_key(key_path, account_col, check_col, None, "gap")
    reported, unsupported = load_reported(str(run_id), "question_ref")
    s = score(truth, reported, unsupported)
    with connect() as conn:
        conn.execute(
            """INSERT INTO audit.run_scores (run_id, key_name, true_gaps, reported_gaps, matched, false_gaps, unsupported, recall, false_gap_rate, scored_by)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (run_id, key_path.name, s.true_gaps, s.reported_gaps, s.matched, len(s.false_gaps), s.unsupported_claims, round(s.recall, 4), round(s.false_gap_rate, 4), scored_by))
    return {"key": key_path.name, "true_gaps": s.true_gaps, "reported_gaps": s.reported_gaps, "matched": s.matched, "recall": s.recall, "false_gap_rate": s.false_gap_rate,
            "unsupported_claims": s.unsupported_claims, "passes": s.passes, "missed": [list(k) for k in s.missed], "false_gaps": [list(k) for k in s.false_gaps]}


SLA_SECONDS = 2 * 3600  # 300 accounts and 10 questions in under two hours


def acceptance(run_id: UUID) -> dict:
    """The acceptance criteria for one audit, as far as they can be known: recall and false gaps need an answer key (none exists for a hidden request),
    the rest are measured on every audit."""
    with connect() as conn:
        score = conn.execute("SELECT * FROM audit.run_scores WHERE run_id = %s ORDER BY score_id DESC LIMIT 1", (run_id,)).fetchone()
        unsupported = conn.execute("SELECT count(*) AS n FROM audit.v_unsupported_claims WHERE run_id = %s", (run_id,)).fetchone()["n"]
        cites = conn.execute("SELECT checked, verified FROM audit.citation_checks WHERE run_id = %s", (run_id,)).fetchone()
        run = conn.execute("SELECT status, EXTRACT(EPOCH FROM (finished_at - started_at))::int AS seconds FROM audit.runs WHERE run_id = %s", (run_id,)).fetchone()
    return {"score": ({"key": score["key_name"], "recall": float(score["recall"]), "false_gap_rate": float(score["false_gap_rate"]), "matched": score["matched"],
                       "true_gaps": score["true_gaps"], "false_gaps": score["false_gaps"], "reported_gaps": score["reported_gaps"]} if score else None),
            "unsupported": unsupported, "citations": dict(cites) if cites else None, "seconds": run["seconds"] if run else None, "sla_seconds": SLA_SECONDS,
            "targets": {"recall": 0.95, "false_gap_rate": 0.05}}
