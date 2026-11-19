"""Score a run against a gap key. The acceptance bar from the problem statement:

  gap recall            >= 95%   true gaps we reported / all true gaps
  false-gap rate        <  5%    reported gaps that are not true gaps / all reported gaps
  unsupported claims    == 0     evidenced or gap findings with no citation

Definition of false-gap rate is our reading of "false gaps under 5%" (docs/decisions.md D-006).

Gap key: CSV with at least account_id and a check column. The check column is matched to our
findings by question_ref by default (--match question_ref) or check_type (--match check_type).
Run `python -m eval.score --inspect <file>` first to see the columns of a new gap key.

  python -m eval.score --run <run_id> --gap-key eval/gap_keys/PUB-01.csv
  python -m eval.score --run <run_id> --gap-key ... --strict     # exit 1 if below the bar
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

TARGET_RECALL = 0.95
TARGET_FALSE_GAP = 0.05

Key = tuple[str, str]  # (account_id, check)


@dataclass
class Score:
    true_gaps: int
    reported_gaps: int
    matched: int
    recall: float
    false_gap_rate: float
    unsupported_claims: int
    missed: list[Key]
    false_gaps: list[Key]

    @property
    def passes(self) -> bool:
        return (self.recall >= TARGET_RECALL and self.false_gap_rate < TARGET_FALSE_GAP
                and self.unsupported_claims == 0)


def _norm(v: str | None) -> str:
    return (v or "").strip().upper()


def score(true_gaps: set[Key], reported_gaps: set[Key], unsupported_claims: int) -> Score:
    matched = true_gaps & reported_gaps
    recall = len(matched) / len(true_gaps) if true_gaps else 1.0
    false = reported_gaps - true_gaps
    fgr = len(false) / len(reported_gaps) if reported_gaps else 0.0
    return Score(len(true_gaps), len(reported_gaps), len(matched), recall, fgr, unsupported_claims,
                 sorted(true_gaps - reported_gaps), sorted(false))


def load_gap_key(path: Path, account_col: str, check_col: str, status_col: str | None,
                 gap_value: str) -> set[Key]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return set()
    missing = [c for c in (account_col, check_col, status_col) if c and c not in rows[0]]
    if missing:
        sys.exit(f"Gap key {path} has no column(s) {missing}. Columns: {list(rows[0])}. "
                 "Pass --account-col / --check-col / --status-col.")
    return {(_norm(r[account_col]), _norm(r[check_col])) for r in rows
            if status_col is None or _norm(r[status_col]) == _norm(gap_value)}


def load_reported(run_id: str, match: str) -> tuple[set[Key], int]:
    from agent.db import connect  # imported here so scoring logic is testable without a DB
    with connect() as conn:
        gaps = conn.execute(
            f"""SELECT DISTINCT f.account_id, c.{match} AS chk
                FROM audit.findings f JOIN audit.checks c USING (run_id, check_id)
                WHERE f.run_id = %s AND f.status = 'gap'""", (run_id,)).fetchall()
        unsupported = conn.execute(
            "SELECT count(*) AS n FROM audit.v_unsupported_claims WHERE run_id = %s",
            (run_id,)).fetchone()["n"]
    return {(_norm(r["account_id"]), _norm(r["chk"])) for r in gaps}, unsupported


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run")
    ap.add_argument("--gap-key", type=Path)
    ap.add_argument("--inspect", type=Path, help="print the columns and first rows of a gap key")
    ap.add_argument("--match", choices=["question_ref", "check_type"], default="question_ref")
    ap.add_argument("--account-col", default="account_id")
    ap.add_argument("--check-col", default="question_ref")
    ap.add_argument("--status-col", default=None, help="if the key lists all rows, the status column")
    ap.add_argument("--gap-value", default="gap")
    ap.add_argument("--json", type=Path, help="also write the score as JSON here")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    if a.inspect:
        with a.inspect.open(newline="", encoding="utf-8-sig") as f:
            r = csv.reader(f)
            for i, row in enumerate(r):
                print(row)
                if i == 5:
                    break
        return
    if not (a.run and a.gap_key):
        ap.error("--run and --gap-key are required")

    truth = load_gap_key(a.gap_key, a.account_col, a.check_col, a.status_col, a.gap_value)
    reported, unsupported = load_reported(a.run, a.match)
    s = score(truth, reported, unsupported)

    ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    print(f"gap recall          {s.recall:7.1%}  ({s.matched}/{s.true_gaps})        "
          f"{ok(s.recall >= TARGET_RECALL)}  target >= {TARGET_RECALL:.0%}")
    print(f"false-gap rate      {s.false_gap_rate:7.1%}  ({len(s.false_gaps)}/{s.reported_gaps})        "
          f"{ok(s.false_gap_rate < TARGET_FALSE_GAP)}  target < {TARGET_FALSE_GAP:.0%}")
    print(f"unsupported claims  {s.unsupported_claims:7d}                {ok(s.unsupported_claims == 0)}  target 0")
    for label, items in (("missed", s.missed), ("false", s.false_gaps)):
        if items:
            print(f"\n{label} gaps (first 20):")
            for acct, chk in items[:20]:
                print(f"  {acct}  {chk}")
    if a.json:
        a.json.write_text(json.dumps({**asdict(s), "passes": s.passes}, indent=2))
    if a.strict and not s.passes:
        sys.exit(1)


if __name__ == "__main__":
    main()
