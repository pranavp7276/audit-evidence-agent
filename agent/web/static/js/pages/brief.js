import { esc, num, fdate, badge, sevBadge } from "../core.js";

/* A one-page status for the relationship manager: what the lender asked, what was found, what is being done about it, and when the response is due.
   Plain words, no tool or record detail; every number is the same one the audit shows, and the evidence pack holds the records behind it. */

const disp = (review, status, d) => review.filter((r) => r.status === status && r.disposition === d).reduce((a, r) => a + +r.n, 0);

export function briefTab(el, d, runId, scale) {
  const { run, checks, totals: t, severity, review, letter, coverage } = d;
  const due = run.response_due ? new Date(String(run.response_due).slice(0, 10) + "T00:00:00") : null;
  const days = due ? Math.round((due - new Date(new Date().toDateString())) / 86400000) : null;
  const gaps = review.filter((r) => r.status === "gap").reduce((a, r) => a + +r.n, 0);
  const open = disp(review, "gap", "open"), confirmed = disp(review, "gap", "confirmed"), disputed = disp(review, "gap", "disputed"), plan = disp(review, "gap", "remediation_planned");
  const agencyDocs = checks.filter((c) => c.check_type === "other" && (c.test_definition.triage || {}).kind === "vendor_document");
  const untestable = checks.filter((c) => c.check_type === "other" && (c.test_definition.triage || {}).kind !== "vendor_document");
  const tested = checks.filter((c) => c.check_type !== "other");
  const line = (c) => {
    const g = +c.accounts_gap, u = +c.accounts_unknown, ok = +c.accounts_ok;
    return `<tr><td><strong>${esc(c.question_ref)}</strong></td><td>${esc(c.question_text)}</td>
      <td>${g ? `<strong style="color:var(--gap)">${num(g)} account${g === 1 ? "" : "s"} with a gap</strong>` : "No gaps found"}${u ? `<div class="small muted">${num(u)} could not be determined</div>` : ""}<div class="small muted">${num(ok)} shown compliant</div></td></tr>`;
  };
  el.innerHTML = `<div class="brief">
    <div class="row between no-print"><p class="muted small" style="margin:0">A one-page status for the lender relationship. Print it or save it as a PDF.</p><button onclick="window.print()">Print / save as PDF</button></div>
    <h2 style="margin-top:12px">${esc(run.lender || "The lender")}: audit ${esc(run.request_id)}</h2>
    <div class="grid cols3" style="margin:10px 0">
      <div class="stat"><div class="l">Response due</div><div class="n" style="font-size:20px">${due ? fdate(run.response_due) : "not set"}</div><div class="l">${days == null ? "" : days < 0 ? `${-days} day(s) overdue` : days === 0 ? "due today" : `${days} day(s) left`}</div></div>
      <div class="stat"><div class="l">Response letter</div><div class="n" style="font-size:20px">${letter ? esc(letter.status.replace("_", " ")) : "not started"}</div><div class="l">${letter ? `version ${letter.version}` : "drafted from the findings once they are reviewed"}</div></div>
      <div class="stat"><div class="l">Accounts tested</div><div class="n" style="font-size:20px">${num(coverage.sampled)}</div><div class="l">${num(tested.length)} test${tested.length === 1 ? "" : "s"}</div></div>
    </div>
    <h3>What we found</h3>
    <p>${+t.gap ? `We found <strong>${num(t.gap)} gap${+t.gap === 1 ? "" : "s"}</strong> across <strong>${num(t.accounts_with_gaps)}</strong> of the ${num(coverage.sampled)} accounts tested: ${severity.map((s) => `${num(s.findings)} ${esc(s.severity)}`).join(", ")}.` : "We found no gaps."}
      ${+t.cannot_determine ? `${num(t.cannot_determine)} item${+t.cannot_determine === 1 ? "" : "s"} could not be determined from the records and are being followed up; we make no claim about them.` : ""}
      Every figure points at the records behind it in the evidence pack.</p>
    <table><thead><tr><th style="width:60px">Ref</th><th>What the lender asked</th><th>Result</th></tr></thead><tbody>${tested.map(line).join("")}</tbody></table>
    ${agencyDocs.length ? `<h3>Documents the agency must supply</h3><p class="small muted" style="margin-top:0">These are agency records that none of our systems hold, so nothing is claimed about them until they arrive.</p><ul>${agencyDocs.map((c) => `<li><strong>${esc(c.question_ref)}</strong> ${esc(c.question_text)}</li>`).join("")}</ul>` : ""}
    ${untestable.length ? `<h3>What cannot be shown from our systems</h3><ul>${untestable.map((c) => `<li><strong>${esc(c.question_ref)}</strong> ${esc(c.question_text)}</li>`).join("")}</ul>` : ""}
    <h3>What we are doing about the gaps</h3>
    ${gaps ? `<table><tbody><tr><td>Not yet reviewed</td><td class="num"><strong>${num(open)}</strong></td></tr><tr><td>Confirmed as gaps</td><td class="num"><strong>${num(confirmed)}</strong></td></tr>
      <tr><td>Remediation planned</td><td class="num"><strong>${num(plan)}</strong></td></tr><tr><td>Disputed by the business (still reported until the evidence changes)</td><td class="num"><strong>${num(disputed)}</strong></td></tr></tbody></table>` : `<p>No gaps to act on.</p>`}
    <p class="small muted">Fixing gaps is outside this audit. This page reports what was found and who has looked at it.</p>
  </div>`;
}
