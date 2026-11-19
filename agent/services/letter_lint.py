"""The letter's claims check: a statement of fact in the response letter must point at what it rests on, and its numbers must match.

The draft letter marks every statement of fact with a reference: [F123] a finding, [Q3] the results of a check, [R] the totals for the whole
audit. This check reads the letter as it now stands, including the auditor's edits, and reports:

  - a sentence that states a result (a number, "gap", "evidenced", "compliant", "accounts tested") with no reference
  - a reference that does not exist in this audit, or a finding that belongs to a different account than the sentence names
  - a number that differs from what the findings show: the headline, the severity table, the per-question table, a result sentence

Management's own comments are their words and are not checked. A letter with problems can still be saved as a draft; it cannot be approved.
"""
from __future__ import annotations

import re
from collections import Counter
from uuid import UUID

from agent.services.pack import collect

_TOKEN = re.compile(r"\[(F\d+|R|[A-Za-z][A-Za-z0-9]*)\]")
_CLAIM_WORDS = re.compile(r"\d|\bgaps?\b|\bevidenced\b|\bcompliant\b|\bcompliance\b|\btested\b", re.IGNORECASE)
_HEADLINE = re.compile(r"We found \*\*(\d+) gap\(s\) affecting (\d+) of (\d+) sampled accounts\*\*")
_RESULT = re.compile(r"of (\d+) sampled accounts, (\d+) were evidenced as compliant, (\d+) have at least one gap \((\d+) gap finding\(s\)\) and (\d+) could not be determined")
_EXEMPT_PREFIXES = ("**what we tested:**", "**to:**", "**date:**", "**status:**")


def _facts(d: dict) -> dict:
    """What the findings show, recomputed from the database."""
    by_check: dict[str, list[dict]] = {}
    for f in d["findings"]:
        by_check.setdefault(f["check_id"], []).append(f)
    checks = {}
    for c in d["checks"]:
        fs = by_check.get(c["check_id"], [])
        g = {f["account_id"] for f in fs if f["status"] == "gap"}
        e = {f["account_id"] for f in fs if f["status"] == "evidenced"} - g
        u = {f["account_id"] for f in fs} - g - e
        checks[c["check_id"]] = {"ref": c["question_ref"], "tested": d["sample_n"].get(c["check_id"], 0), "evidenced": len(e), "gap_accounts": len(g),
                                 "gap_findings": sum(f["status"] == "gap" for f in fs), "unknown": len(u)}
    gaps = [f for f in d["findings"] if f["status"] == "gap"]
    return {"checks": checks, "gap_total": len(gaps), "gap_accounts": len({f["account_id"] for f in gaps}),
            "sample": max(d["sample_n"].values(), default=0), "severity": Counter(f["severity"] for f in gaps),
            "findings": {f["finding_id"]: f for f in d["findings"]}}


def lint(run_id: UUID, body: str) -> list[dict]:
    """Problems found in the letter, each {line, text, problem}. An empty list means every claim is referenced and its numbers match."""
    facts = _facts(collect(run_id))
    problems: list[dict] = []

    def flag(n: int, text: str, problem: str) -> None:
        problems.append({"line": n, "text": text.strip()[:240], "problem": problem})

    section, table, in_comment = "", "", False
    for n, raw in enumerate(body.split("\n"), 1):
        line = raw.strip()
        if raw.startswith("## "):
            section, table, in_comment = raw[3:].split(".")[0].strip().lower(), "", False
            continue
        if not line or line.startswith("#"):
            in_comment = False
            table = "" if not line else table
            continue
        if line.lower().startswith("**management comment:**"):
            in_comment = not line.rstrip().endswith("**")  # a comment may run on over following lines until a blank line
            continue
        if in_comment or section not in ("2", "3", "3a") or line.lower().startswith(_EXEMPT_PREFIXES):
            continue
        tokens = _TOKEN.findall(line)

        # references must exist, and a finding reference must name the account the sentence is about
        for t in tokens:
            if t == "R":
                continue
            if t.startswith("F") and t[1:].isdigit():
                f = facts["findings"].get(int(t[1:]))
                if f is None:
                    flag(n, line, f"{t} is not a finding in this audit.")
                elif line.startswith("- ") and str(f["account_id"]) not in line:
                    flag(n, line, f"{t} belongs to account {f['account_id']}, which this line does not name.")
            elif t not in facts["checks"] and t not in {c["ref"] for c in facts["checks"].values()}:
                flag(n, line, f"{t} is not a question or check in this audit.")

        # numbers must match the findings
        if m := _HEADLINE.search(line):
            got, want = tuple(map(int, m.groups())), (facts["gap_total"], facts["gap_accounts"], facts["sample"])
            if got != want:
                flag(n, line, f"The findings show {want[0]} gap(s) affecting {want[1]} of {want[2]} sampled accounts.")
        if m := _RESULT.search(line):
            check = next((facts["checks"][t] for t in tokens if t in facts["checks"]), None)
            if check:
                got = tuple(map(int, m.groups()))
                want = (check["tested"], check["evidenced"], check["gap_accounts"], check["gap_findings"], check["unknown"])
                if got != want:
                    flag(n, line, f"The findings show {want[0]} tested, {want[1]} evidenced, {want[2]} with gaps ({want[3]} findings), {want[4]} undetermined.")
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if cells[0] in ("Severity", "Question"):
                table = cells[0]
                continue
            if table == "Severity" and len(cells) == 2 and cells[1].isdigit() and int(cells[1]) != facts["severity"].get(cells[0], 0):
                flag(n, line, f"The findings show {facts['severity'].get(cells[0], 0)} {cells[0]} gap finding(s).")
            elif table == "Question" and len(cells) == 6 and all(c.isdigit() for c in cells[2:]):
                check = facts["checks"].get(cells[1].split(" ")[0])
                if check and tuple(map(int, cells[2:])) != (check["tested"], check["evidenced"], check["gap_accounts"], check["unknown"]):
                    flag(n, line, f"The findings show {check['tested']} tested, {check['evidenced']} evidenced, {check['gap_accounts']} with gaps, {check['unknown']} undetermined.")
            continue

        if not tokens and _CLAIM_WORDS.search(line):
            flag(n, line, "This states a result but points at no finding or check. Add its reference, or remove the statement.")
    return problems
