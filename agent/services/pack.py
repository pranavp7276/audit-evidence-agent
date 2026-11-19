"""Build the evidence pack, gap report and draft letter, only from audit.* for one run.

The writer never adds a factual statement that is not a row in audit.findings / audit.citations.
The letter is generated from those rows by a template (no LLM prose); each section keeps the question it
answers so a reviewer can trace it, and management comments are the auditor's own text, never invented.

Outputs, under out/<request_id>/<run_id>/:
  index.md                  per question: checks, counts, links to extracts
  extracts/<check>.csv      one row per finding with its citations and review status
  gap_report.csv            every gap, ordered by severity scale, with review status
  follow_up.csv             findings that could not be determined, to chase manually
  reviews.csv               the full review trail (who decided what, when)
  response_letter.md        the saved letter if one exists, else a freshly generated draft
  rules_and_assumptions.md  what each check tests and the interpretations applied
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from uuid import UUID

from agent.core.db import connect

OUT = Path(__file__).resolve().parents[2] / "out"
_STATUSES = ("evidenced", "gap", "cannot_determine")
DISPOSITIONS = {"open": "Open", "confirmed": "Confirmed", "disputed": "Disputed",
                "remediation_planned": "Remediation planned", "evidence_obtained": "Evidence obtained"}


def collect(run_id: UUID) -> dict:
    """Everything the pack and the letter are built from, read once from audit.*."""
    with connect() as conn:
        run = conn.execute("SELECT * FROM audit.runs WHERE run_id = %s", (run_id,)).fetchone()
        checks = conn.execute("SELECT * FROM audit.checks WHERE run_id = %s ORDER BY check_id", (run_id,)).fetchall()
        findings = conn.execute(
            """SELECT f.*, r.disposition, r.comment AS review_comment, r.reviewer, r.created_at AS reviewed_at
               FROM audit.findings f
               LEFT JOIN LATERAL (SELECT * FROM audit.finding_reviews x WHERE x.finding_id = f.finding_id
                                  ORDER BY x.review_id DESC LIMIT 1) r ON true
               WHERE f.run_id = %s ORDER BY f.finding_id""", (run_id,)).fetchall()
        cites = defaultdict(list)
        for c in conn.execute(
                "SELECT c.* FROM audit.citations c JOIN audit.findings f USING (finding_id) WHERE f.run_id = %s "
                "ORDER BY c.citation_id", (run_id,)):
            cites[c["finding_id"]].append(c)
        sample_n = {r["check_id"]: r["n"] for r in conn.execute(
            "SELECT check_id, count(*) AS n FROM audit.sample_accounts WHERE run_id = %s GROUP BY check_id", (run_id,))}
        responses = {r["question_ref"]: r for r in conn.execute(
            "SELECT DISTINCT ON (question_ref) * FROM audit.question_responses WHERE run_id = %s "
            "ORDER BY question_ref, response_id DESC", (run_id,))}
        letter = conn.execute("SELECT * FROM audit.letters WHERE run_id = %s ORDER BY version DESC LIMIT 1", (run_id,)).fetchone()
        reviews = conn.execute(
            """SELECT r.*, f.check_id, f.account_id, f.subject_ref FROM audit.finding_reviews r
               JOIN audit.findings f USING (finding_id) WHERE r.run_id = %s ORDER BY r.review_id""", (run_id,)).fetchall()
    return {"run": run, "checks": checks, "findings": findings, "cites": cites, "sample_n": sample_n,
            "responses": responses, "letter": letter, "reviews": reviews}


def _cites(c: list[dict]) -> str:
    return "; ".join(f"{x['source_system']}:{x['record_key']}" for x in c)


def _weights(checks: list[dict]) -> dict[str, int]:
    """Review-priority weight (1 to 3) of the guardrail each check applied. It orders review only."""
    return {c["check_id"]: int((c["test_definition"] or {}).get("priority_weight", 1)) for c in checks}


def _rank(scale: list[str], weights: dict[str, int] | None = None):
    """Gaps most severe first, then heavier guardrail weight first, then by check and account. Every gap is kept."""
    r, w = {s: i for i, s in enumerate(scale)}, weights or {}
    return lambda f: (r.get(f["severity"], len(r)), -w.get(f["check_id"], 1), f["check_id"], f["account_id"], f["subject_ref"] or "")


def _question_groups(d: dict) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for c in d["checks"]:
        groups.setdefault(c["question_ref"], []).append(c)
    return groups


def generate_letter(run_id: UUID) -> str:
    """A draft response letter from the recorded findings, reviews and management comments."""
    from agent.checks.catalog import ASSUMPTIONS, CHECK_INFO

    d = collect(run_id)
    run, findings = d["run"], d["findings"]
    scale = list(run["severity_scale"] or [])
    by_check = defaultdict(list)
    for f in findings:
        by_check[f["check_id"]].append(f)
    sample = max(d["sample_n"].values(), default=0)
    gaps = [f for f in findings if f["status"] == "gap"]
    n_acc_gap = len({f["account_id"] for f in gaps})
    out = [f"# Response to audit request {run['request_id']}", "",
           f"**To:** {run['lender'] or '[Requesting lender or regulator]'}  ",
           f"**Date:** {date.today():%d %B %Y}  ",
           "**Status:** DRAFT for compliance review. Not for release until approved.", "",
           "## 1. Scope and approach", "",
           f"We tested {len(d['checks'])} check(s) drawn from the questions in your request across {sample} sampled accounts, "
           "using the contact log, consent registry, identity verification, recording store, notice dispatch history, "
           "holiday calendar and certification register. Calling hours and frequency limits are taken from the policy limits (D12). "
           "All times are compared in UTC. Every statement below is traced to the recorded findings and the source records they cite; "
           "gaps are reported as found.", "",
           "## 2. Summary of results", "",
           f"We found **{len(gaps)} gap(s) affecting {n_acc_gap} of {sample} sampled accounts**.", ""]
    sev = Counter(f["severity"] for f in gaps)
    if sev:
        out += ["| Severity | Gap findings |", "|---|---|"]
        out += [f"| {s} | {sev[s]} |" for s in scale if s in sev]
        out += [f"| {s} | {n} |" for s, n in sev.items() if s not in scale]
        out.append("")
    out += ["| Question | Check | Accounts tested | Evidenced | With gaps | Cannot determine |", "|---|---|---|---|---|---|"]
    for c in d["checks"]:
        fs = by_check[c["check_id"]]
        g = {f["account_id"] for f in fs if f["status"] == "gap"}
        e = {f["account_id"] for f in fs if f["status"] == "evidenced"} - g
        u = {f["account_id"] for f in fs} - g - e
        out.append(f"| {c['question_ref']} | {c['check_id']} {CHECK_INFO[c['check_type']]['title']} | {d['sample_n'].get(c['check_id'], 0)} "
                   f"| {len(e)} | {len(g)} | {len(u)} |")
    out += ["", "## 3. Responses by question", ""]
    for ref, cs in _question_groups(d).items():
        out += [f"### {ref}. {cs[0]['question_text']}", ""]
        for c in cs:
            info, fs = CHECK_INFO[c["check_type"]], by_check[c["check_id"]]
            if c["check_type"] == "other":
                out += ["This question could not be mapped to a test and has **not** been answered by the platform. "
                        "It needs a manual response.", ""]
                continue
            g = [f for f in fs if f["status"] == "gap"]
            ga = {f["account_id"] for f in g}
            ea = {f["account_id"] for f in fs if f["status"] == "evidenced"} - ga
            ua = {f["account_id"] for f in fs} - ga - ea
            out += [f"**What we tested:** {info['tests']}", "",
                    f"**Result:** of {d['sample_n'].get(c['check_id'], 0)} sampled accounts, {len(ea)} were evidenced as compliant, "
                    f"{len(ga)} have at least one gap ({len(g)} gap finding(s)) and {len(ua)} could not be determined.", ""]
            if g:
                bysev = Counter(f["severity"] for f in g)
                out += ["**Gaps, stated as found:** " + ", ".join(f"{k}: {v}" for k, v in bysev.items()) + ".", ""]
                out += [f"- {f['account_id']} ({f['subject_ref'] or 'account'}): {f['reason']}" for f in sorted(g, key=_rank(scale, _weights(d["checks"])))[:5]]
                if len(g) > 5:
                    out.append(f"- ... and {len(g) - 5} more; see the gap report (annex).")
                disp = Counter(f["disposition"] or "open" for f in g)
                out += ["", "**Review status of these gaps:** " + ", ".join(f"{DISPOSITIONS[k].lower()}: {v}" for k, v in disp.items())
                        + ". A disputed gap remains reported until the evidence changes.", ""]
            if ua:
                out += [f"{len(ua)} account(s) could not be determined from the available evidence; these are being followed up "
                        "and no compliance is claimed for them.", ""]
        resp = d["responses"].get(ref)
        out += [f"**Management comment:** {resp['body']}" if resp else "**Management comment:** [To be completed by management]", ""]
    out += ["## 4. Limitations and assumptions", ""] + [f"- **{k}.** {v}" for k, v in ASSUMPTIONS] + [
        "", "## Annexes", "", "- Annex A: gap report (gap_report.csv)", "- Annex B: evidence extracts per check (extracts/)",
        "- Annex C: items for follow-up (follow_up.csv)", "- Annex D: review trail (reviews.csv)", ""]
    return "\n".join(out)


def build_pack(run_id: UUID) -> str:
    """Write the pack and return its folder."""
    from agent.checks.catalog import ASSUMPTIONS, CHECK_INFO, STATUS_MEANING

    d = collect(run_id)
    run, checks, findings, cites = d["run"], d["checks"], d["findings"], d["cites"]
    folder = OUT / run["request_id"] / str(run_id)
    (folder / "extracts").mkdir(parents=True, exist_ok=True)
    scale = list(run["severity_scale"])
    by_check = defaultdict(list)
    for f in findings:
        by_check[f["check_id"]].append(f)
    qref = {c["check_id"]: c["question_ref"] for c in checks}

    def review(f: dict) -> list:
        return [DISPOSITIONS.get(f["disposition"] or "open", "Open"), f["reviewer"] or "", f["review_comment"] or ""]

    for chk in checks:
        with (folder / "extracts" / f"{chk['check_id']}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["finding_id", "account_id", "subject_ref", "status", "severity", "reason", "citations", "extracts",
                        "review_status", "reviewer", "review_comment"])
            for f in by_check[chk["check_id"]]:
                cs = cites[f["finding_id"]]
                w.writerow([f["finding_id"], f["account_id"], f["subject_ref"] or "", f["status"], f["severity"] or "",
                            f["reason"], _cites(cs), json.dumps([c["extract"] for c in cs if c["extract"]]), *review(f)])

    weights = _weights(checks)
    gaps = sorted((f for f in findings if f["status"] == "gap"), key=_rank(scale, weights))
    with (folder / "gap_report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["severity", "priority_weight", "question_ref", "check_id", "account_id", "subject_ref", "reason", "citations", "finding_id",
                    "review_status", "reviewer", "review_comment"])
        for f in gaps:
            w.writerow([f["severity"], weights.get(f["check_id"], 1), qref[f["check_id"]], f["check_id"], f["account_id"], f["subject_ref"] or "",
                        f["reason"], _cites(cites[f["finding_id"]]), f["finding_id"], *review(f)])
    with (folder / "follow_up.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["question_ref", "check_id", "account_id", "subject_ref", "why", "finding_id", "review_status", "reviewer", "review_comment"])
        for f in findings:
            if f["status"] == "cannot_determine":
                w.writerow([qref[f["check_id"]], f["check_id"], f["account_id"], f["subject_ref"] or "", f["reason"], f["finding_id"], *review(f)])
    with (folder / "reviews.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["when", "reviewer", "finding_id", "check_id", "account_id", "subject_ref", "disposition", "comment"])
        for r in d["reviews"]:
            w.writerow([r["created_at"].isoformat(), r["reviewer"], r["finding_id"], r["check_id"], r["account_id"],
                        r["subject_ref"] or "", DISPOSITIONS[r["disposition"]], r["comment"] or ""])

    with connect() as conn:
        trace = conn.execute("SELECT seq, phase, agent, action, tool, check_id, account_id, status, duration_ms FROM audit.agent_steps WHERE run_id = %s ORDER BY seq",
                             (run_id,)).fetchall()
    with (folder / "agent_trace.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["seq", "phase", "agent", "action", "tool", "check_id", "account_id", "status", "duration_ms"])
        for t in trace:
            w.writerow([t["seq"], t["phase"], t["agent"], t["action"], t["tool"] or "", t["check_id"] or "", t["account_id"] or "", t["status"], t["duration_ms"] or ""])

    lines = [f"# Evidence pack: {run['request_id']}", "", f"Run `{run_id}` ({run['status']}), agent version {run['agent_version']}.", ""]
    if run["lender"]:
        lines += [f"Requested by: {run['lender']}", ""]
    lines += ["| Check | Question | Type | Accounts sampled | Evidenced | Gap | Cannot determine | Extract |", "|---|---|---|---|---|---|---|---|"]
    for chk in checks:
        n = Counter(f["status"] for f in by_check[chk["check_id"]])
        lines.append(f"| {chk['check_id']} | {chk['question_ref']} | {chk['check_type']} | {d['sample_n'].get(chk['check_id'], 0)} | "
                     + " | ".join(str(n[s]) for s in _STATUSES) + f" | [csv](extracts/{chk['check_id']}.csv) |")
    lines += ["", f"- Gap report: gap_report.csv ({len(gaps)} gap findings, graded {' > '.join(scale) or 'by severity'})",
              "- Follow-up list: follow_up.csv", "- Review trail: reviews.csv", f"- What the agent did: agent_trace.csv ({len(trace)} steps)", "- Response letter: response_letter.md",
              "- Rules and assumptions: rules_and_assumptions.md", ""]
    (folder / "index.md").write_text("\n".join(lines), encoding="utf-8")

    (folder / "response_letter.md").write_text(d["letter"]["body"] if d["letter"] else generate_letter(run_id), encoding="utf-8")

    rules = ["# Rules and assumptions", "", "## What each check tests", ""]
    for key, info in CHECK_INFO.items():
        if key == "other":
            continue
        rules += [f"### {info['title']} (`{key}`)", f"- Tests: {info['tests']}", f"- Gap: {info['gap']}", f"- Cannot determine: {info['unknown']}",
                  f"- Sources: {', '.join(info['sources'])}", ""]
    rules += ["## Result statuses", ""] + [f"- **{k}**: {v}" for k, v in STATUS_MEANING.items()]
    rules += ["", "## Assumptions", ""] + [f"- **{k}.** {v}" for k, v in ASSUMPTIONS] + [""]
    (folder / "rules_and_assumptions.md").write_text("\n".join(rules), encoding="utf-8")
    return str(folder)
