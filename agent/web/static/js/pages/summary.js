import { esc, num, pct, stat, sevBadge, stackBar, navigate } from "../core.js";
import { acceptanceCard, trapsCard } from "./acceptance.js";

export function summary(el, d, runId, scale, traps = []) {
  const { checks, totals, severity, coverage, collectors, months, review, letter } = d;
  const gaps = +totals.gap, sampled = coverage.sampled;
  const crit = severity[0];
  const rv = (status, disp) => review.filter((r) => r.status === status && (disp === undefined || r.disposition === disp)).reduce((a, r) => a + +r.n, 0);
  const flagged = (d.challenges.disputes || 0) + (d.challenges.unclear || 0);
  const gapsTotal = rv("gap"), gapsOpen = rv("gap", "open"), cndTotal = rv("cannot_determine"), cndOpen = rv("cannot_determine", "open");
  const verdictCls = !gaps ? "good" : crit && scale.length && crit.severity === scale[0] ? "bad" : "warn";
  const maxM = Math.max(1, ...months.map((m) => +m.gaps));
  const step = (done, partial, title, sub, link) => `<li class="${done ? "done" : partial ? "partial" : ""}"><span class="dot">${done ? "&#10003;" : ""}</span><div class="t"><strong>${title}</strong><div class="s">${sub}</div></div>${link ? `<a class="btn no-print" href="${link}">Open</a>` : ""}</li>`;
  el.innerHTML = `
    ${d.run.status === "running" ? "" : `<div class="banner ${verdictCls}"><div class="big">${gaps ? `${num(gaps)} gap${gaps === 1 ? "" : "s"} found across ${num(totals.accounts_with_gaps)} of ${num(sampled)} sampled accounts` : `No gaps found in ${num(sampled)} sampled accounts`}</div>
      <div class="muted">${severity.map((s) => `${num(s.findings)} ${esc(s.severity)}`).join(" · ")}${totals.cannot_determine ? `${gaps ? " · " : ""}${num(totals.cannot_determine)} items could not be determined and need follow-up` : ""}. Nothing is claimed as compliant without a cited record.</div></div>`}
    ${coverage.unresolved.length ? `<div class="note"><strong>Sample coverage:</strong> ${coverage.unresolved.length} of ${num(coverage.references)} account reference(s) in the request could not be tested: ${coverage.unresolved.filter((x) => x.status === "unmatched").length} matched no loan account, ${coverage.unresolved.filter((x) => x.status === "ambiguous").length} matched more than one (${coverage.unresolved.slice(0, 4).map((x) => esc(x.ref)).join(", ")}${coverage.unresolved.length > 4 ? ", …" : ""}). They are listed in the Accounts tab and need Compliance to resolve them.</div>` : ""}
    ${coverage.no_data.length ? `<div class="note"><strong>No activity:</strong> ${coverage.no_data.length} sampled account(s) have no calls or messages on record (${coverage.no_data.slice(0, 6).map(esc).join(", ")}${coverage.no_data.length > 6 ? ", …" : ""}).</div>` : ""}
    <div class="grid cols4">${stat(d.questions, "questions in the request")}${stat(totals.evidenced, "evidenced results", "ok")}${stat(gaps, "gap findings", "gap")}${stat(totals.cannot_determine, "cannot determine", "unk")}</div>
    <div class="grid cols2" style="margin-top:14px;align-items:start">${acceptanceCard(d.acceptance, runId)}${trapsCard(traps, "Subtle traps in this audit's evidence")}</div>
    <div class="grid cols2" style="margin-top:14px">
      <div class="card"><h2>Your next steps</h2><ul class="todo">
        ${step(!coverage.unresolved.length && !coverage.no_data.length, false, "Check the sample", coverage.unresolved.length ? `${coverage.unresolved.length} account references are unmatched or ambiguous` : coverage.no_data.length ? `${coverage.no_data.length} sampled accounts have no activity` : `All ${num(sampled)} sampled accounts matched and have activity`, "")}
        ${flagged ? step(false, false, "Read the gaps the second reading flagged", `${flagged} gap(s) the second model disputes or could not confirm: review these first`, `#/run/${runId}/gaps?challenge=flagged`) : ""}
        ${step(gapsTotal > 0 && gapsOpen === 0 || !gapsTotal, gapsTotal > gapsOpen, "Review the gaps", gapsTotal ? `${num(gapsTotal - gapsOpen)} of ${num(gapsTotal)} reviewed` : "No gaps to review", gapsTotal ? `#/run/${runId}/gaps` : "")}
        ${step(!cndTotal || cndOpen === 0, cndTotal > cndOpen, "Follow up what could not be determined", cndTotal ? `${num(cndTotal - cndOpen)} of ${num(cndTotal)} followed up` : "Nothing to follow up", cndTotal ? `#/run/${runId}/followup` : "")}
        ${step(d.responses >= d.questions && d.questions > 0, d.responses > 0, "Add management comments", `${d.responses} of ${d.questions} questions have a comment`, `#/run/${runId}/questions`)}
        ${step(letter && letter.status === "approved", !!letter, "Review and approve the response letter", letter ? `Version ${letter.version}: ${letter.status.replace("_", " ")}` : "Not started", `#/run/${runId}/letter`)}
        ${step(false, false, "Release the evidence pack", "Download the zip once the letter is approved", `#/run/${runId}/pack`)}
      </ul></div>
      <div class="card"><h2>Gaps by severity</h2>
        ${severity.length ? severity.map((s) => { const i = Math.max(0, Math.min(scale.indexOf(s.severity), 2)); const mx = Math.max(...severity.map((x) => +x.findings)); return `<div style="margin-bottom:12px"><div class="row between small"><span>${sevBadge(s.severity, scale)}</span><span><strong>${num(s.findings)}</strong> findings · ${num(s.accounts)} accounts</span></div><div class="hbar"><span style="width:${(s.findings / mx) * 100}%;background:var(--sev-${i})"></span></div></div>`; }).join("") : `<div class="empty">No gaps.</div>`}
        <div class="small muted">Severity scale from the request: ${scale.length ? scale.map(esc).join(" › ") : "none given"}.</div></div>
    </div>
    <div class="card"><h2>Results by question</h2>
      <table><thead><tr><th>Check</th><th>Test</th><th class="num">Accounts</th><th>Result</th><th class="num">Compliant</th><th class="num">With gaps</th><th class="num">Cannot determine</th></tr></thead><tbody>
      ${checks.map((c) => `<tr class="click" data-q="${esc(c.question_ref)}"><td><strong>${esc(c.check_id)}</strong></td><td>${esc(c.title)}<div class="small muted">${esc(c.question_text)}</div></td>
        <td class="num">${num(c.accounts)}</td><td style="min-width:130px">${stackBar(+c.accounts_ok, +c.accounts_gap, +c.accounts_unknown)}</td>
        <td class="num">${num(c.accounts_ok)} <span class="muted small">(${pct(+c.accounts_ok, +c.accounts_tested)}%)</span></td>
        <td class="num"><strong style="color:${+c.accounts_gap ? "var(--gap)" : "inherit"}">${num(c.accounts_gap)}</strong></td><td class="num">${num(c.accounts_unknown)}</td></tr>`).join("")}
      </tbody></table></div>
    ${collectors.length || months.length ? `<div class="grid cols2">
      <div class="card"><h2>Where the gaps concentrate: collectors</h2>
        ${collectors.length ? `<table><thead><tr><th>Collector</th><th>Agency</th><th class="num">Gaps</th><th>Questions</th></tr></thead><tbody>${collectors.map((c) => `<tr><td class="mono">${esc(c.collector_id)}</td><td>${esc(c.agency || "")}</td><td class="num"><strong>${num(c.gaps)}</strong></td><td>${(c.questions || []).map((x) => `<span class="tag">${esc(x)}</span>`).join(" ")}</td></tr>`).join("")}</tbody></table>
        <p class="small muted">Collectors behind the most gap findings on calls and messages. Use this to focus remediation.</p>` : `<div class="empty">No collector-level gaps.</div>`}</div>
      <div class="card"><h2>When the gaps occurred</h2>
        ${months.length ? `<div class="cols">${months.map((m) => `<div style="height:${(m.gaps / maxM) * 100}%" title="${esc(m.month)}: ${m.gaps} gaps"></div>`).join("")}</div><div class="cols-l">${months.map((m) => `<span>${esc(m.month.slice(5))}</span>`).join("")}</div>
        <p class="small muted">Gap findings on calls and messages by month (UTC). Frequency, notice and some certificate gaps are not tied to a single message and are not shown.</p>` : `<div class="empty">No dated gaps.</div>`}</div></div>` : ""}
    <div class="no-print"><button onclick="window.print()">Print summary / save as PDF</button></div>`;
  el.querySelectorAll("tr[data-q]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/run/${runId}/questions/${encodeURIComponent(tr.dataset.q)}`)));
}
