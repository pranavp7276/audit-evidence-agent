"""Build the evidence pack, gap report and draft letter, only from audit.* for one run.

The writer never adds a factual statement that is not a row in audit.findings / audit.citations.
The letter is generated from those rows by a template (no LLM prose yet); each paragraph keeps a
list of the finding_ids it rests on so a reviewer can trace it.

Outputs, under out/<request_id>/<run_id>/:
  index.md            per question: checks, counts, links to extracts
  extracts/<check>.csv one row per finding with its citations (only fields the request needs)
  gap_report.csv      from audit.v_gap_report, ordered by severity scale
  response_letter.md  draft for compliance review, gaps stated plainly
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from uuid import UUID

from agent.db import connect

OUT = Path(__file__).resolve().parents[2] / "out"
_STATUSES = ("evidenced", "gap", "cannot_determine")


def _cites(c: dict) -> str:
    return "; ".join(f"{x['source_system']}:{x['record_key']}" for x in c)


def build_pack(run_id: UUID) -> str:
    """Write the pack and return its folder."""
    with connect() as conn:
        run = conn.execute("SELECT * FROM audit.runs WHERE run_id = %s", (run_id,)).fetchone()
        checks = conn.execute("SELECT * FROM audit.checks WHERE run_id = %s ORDER BY check_id", (run_id,)).fetchall()
        findings = conn.execute("SELECT * FROM audit.findings WHERE run_id = %s ORDER BY finding_id", (run_id,)).fetchall()
        cites = defaultdict(list)
        for c in conn.execute(
                "SELECT c.* FROM audit.citations c JOIN audit.findings f USING (finding_id) WHERE f.run_id = %s "
                "ORDER BY c.citation_id", (run_id,)):
            cites[c["finding_id"]].append(c)
        sample_n = {r["check_id"]: r["n"] for r in conn.execute(
            "SELECT check_id, count(*) AS n FROM audit.sample_accounts WHERE run_id = %s GROUP BY check_id", (run_id,))}

    folder = OUT / run["request_id"] / str(run_id)
    (folder / "extracts").mkdir(parents=True, exist_ok=True)
    scale = list(run["severity_scale"])
    rank = {s: i for i, s in enumerate(scale)}
    by_check = defaultdict(list)
    for f in findings:
        by_check[f["check_id"]].append(f)

    # extracts: one row per finding with its citations
    for chk in checks:
        with (folder / "extracts" / f"{chk['check_id']}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["finding_id", "account_id", "subject_ref", "status", "severity", "reason", "citations", "extracts"])
            for f in by_check[chk["check_id"]]:
                cs = cites[f["finding_id"]]
                w.writerow([f["finding_id"], f["account_id"], f["subject_ref"] or "", f["status"], f["severity"] or "",
                            f["reason"], _cites(cs), json.dumps([c["extract"] for c in cs if c["extract"]])])

    # gap report, most severe first
    gaps = sorted((f for f in findings if f["status"] == "gap"),
                  key=lambda f: (rank.get(f["severity"], len(rank)), f["check_id"], f["account_id"], f["subject_ref"] or ""))
    qref = {c["check_id"]: c["question_ref"] for c in checks}
    with (folder / "gap_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["severity", "question_ref", "check_id", "account_id", "subject_ref", "reason", "citations", "finding_id"])
        for f in gaps:
            w.writerow([f["severity"], qref[f["check_id"]], f["check_id"], f["account_id"], f["subject_ref"] or "",
                        f["reason"], _cites(cites[f["finding_id"]]), f["finding_id"]])

    # index
    head = "| Check | Question | Type | Accounts sampled | Evidenced | Gap | Cannot determine | Extract |"
    lines = [f"# Evidence pack: {run['request_id']}", "",
             f"Run `{run_id}` ({run['status']}), agent version {run['agent_version']}.", "",
             head, "|---|---|---|---|---|---|---|---|"]
    for chk in checks:
        n = Counter(f["status"] for f in by_check[chk["check_id"]])
        lines.append(f"| {chk['check_id']} | {chk['question_ref']} | {chk['check_type']} | {sample_n.get(chk['check_id'], 0)} | "
                     + " | ".join(str(n[s]) for s in _STATUSES) + f" | [csv](extracts/{chk['check_id']}.csv) |")
    lines += ["", f"Gap report: [gap_report.csv](gap_report.csv) ({len(gaps)} gap findings).", ""]
    (folder / "index.md").write_text("\n".join(lines), encoding="utf-8")

    # draft response letter
    out = ["# Draft response (for compliance review)", "", f"Re: audit request {run['request_id']}", "",
           "Every statement below is taken from the findings recorded for this run; "
           "the finding ids are given so each can be traced.", ""]
    for chk in checks:
        fs = by_check[chk["check_id"]]
        out.append(f"## {chk['question_ref']} ({chk['check_id']}): {chk['question_text']}")
        if chk["check_type"] == "other":
            out += ["", "This question did not map to a check the agent can test. It has NOT been answered.", ""]
            continue
        n = Counter(f["status"] for f in fs)
        g = [f for f in fs if f["status"] == "gap"]
        accounts = len({f["account_id"] for f in g})
        compliant = len({f["account_id"] for f in fs if f["status"] == "evidenced"})
        text = (f"Of {sample_n.get(chk['check_id'], 0)} sampled accounts, {compliant} "
                f"were evidenced as compliant, {accounts} have at least one gap ({n['gap']} gap finding(s)), and "
                f"{n['cannot_determine']} finding(s) could not be determined.")
        out += ["", text]
        if g:
            sev = Counter(f["severity"] for f in g)
            out.append("Gaps found, stated as found: " + ", ".join(f"{k}: {v}" for k, v in sev.items()) + ".")
            out += [f"- {f['account_id']} ({f['subject_ref'] or 'account'}): {f['reason']}" for f in g[:5]]
            if len(g) > 5:
                out.append(f"- ... and {len(g) - 5} more; see gap_report.csv.")
        ids = [f["finding_id"] for f in fs[:10]]
        more = " and others" if len(fs) > 10 else ""
        out += ["", f"_Basis: findings {ids}{more}; full list in extracts/{chk['check_id']}.csv._", ""]
    (folder / "response_letter.md").write_text("\n".join(out), encoding="utf-8")
    return str(folder)
