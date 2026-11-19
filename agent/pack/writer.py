"""Build the evidence pack, gap report and draft letter, only from audit.* for one run.

The writer never adds a factual statement that is not a row in audit.findings / audit.citations.
Text the LLM writes (the letter's prose) may only rephrase those rows; each paragraph keeps a
list of the finding_ids it rests on so a reviewer can trace it.

Outputs, under out/<request_id>/<run_id>/:
  index.md            per question: checks, counts, links to extracts
  extracts/<check>.csv one row per finding with its citations (only fields the request needs)
  gap_report.csv      from audit.v_gap_report, ordered by severity scale
  response_letter.md  draft for compliance review, gaps stated plainly
"""
from __future__ import annotations

from uuid import UUID


def build_pack(run_id: UUID) -> str:
    """Write the pack and return its folder. TODO(owner)."""
    raise NotImplementedError
