import { api, esc, num, fdate, help, badge, rulebookNav } from "../core.js";

export async function rulesPage(el, standalone, runId, done) {
  const [r, src, cov] = await Promise.all([api("/api/rules"), api("/api/data-sources"), api("/api/evidence-coverage").catch(() => null)]);
  const pol = {}; r.policy.forEach((p) => (pol[p.rule_key] ||= []).push(p));
  const LENDER = { BANK01: "Sahyadri Bank", NBFC01: "Kaveri Finserv", MFI01: "Ganga Microfinance" };
  const when_ = (p) => (p.effective_to ? `${fdate(p.effective_from)} to ${fdate(p.effective_to)}` : `from ${fdate(p.effective_from)}`);
  const lim = (keys) => (keys || []).map((k) => {
    if (!pol[k]) return "";
    const groups = {};
    pol[k].forEach((p) => (groups[p.institution_code || "all lenders"] ||= []).push(p));
    return `<div><span class="muted">${esc(k.replace(/_/g, " "))}</span>${Object.entries(groups).map(([inst, ps]) => `<div class="small">${esc(LENDER[inst] || inst)}: ${ps.map((p) => `<strong>${esc(p.rule_value)}</strong> <span class="muted">(${when_(p)})</span>`).join(", ")}</div>`).join("")}</div>`;
  }).filter(Boolean).join("");
  el.innerHTML = `${standalone ? `${rulebookNav("#/rules")}<h1>Rules &amp; data ${help("data")}</h1><p class="muted">How results are decided, the limits in force, the interpretations the platform applies, and what data it reads. Use this to defend a result to the lender.</p>` : ""}
    <div class="card"><h2>How to read a result</h2><table><tbody>${Object.entries(r.status_meaning).map(([k, v]) => `<tr><td style="width:170px">${badge(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><h2>What each check tests</h2><table><thead><tr><th>Check</th><th>Passes when</th><th>Gap when</th><th>Limits in force (D12)</th><th>Sources</th></tr></thead><tbody>
      ${Object.entries(r.checks).filter(([k]) => k !== "other").map(([k, i]) => `<tr><td><strong>${esc(i.title)}</strong><div class="small muted mono">${esc(k)}</div></td><td>${esc(i.tests)}</td><td>${esc(i.gap)}${i.unknown && !/^None|^n\/a/.test(i.unknown) ? `<div class="small muted">Cannot determine: ${esc(i.unknown)}</div>` : ""}</td><td class="small">${lim(i.limits) || "—"}</td><td class="small">${(i.sources || []).map(esc).join(", ")}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><h2>Assumptions applied</h2><ul>${r.assumptions.map((a) => `<li><strong>${esc(a.topic)}.</strong> ${esc(a.text)}</li>`).join("")}</ul>
      <p class="small muted">These are the platform's current interpretations. If your engagement requires a different one, tell the platform owners before relying on the result.</p></div>
    <div class="card"><h2>Data the platform reads</h2><table><thead><tr><th>Source</th><th class="num">Records</th><th>From</th><th>To</th><th>Source time zone</th></tr></thead><tbody>
      ${src.map((s) => `<tr><td>${esc(s.source)}</td><td class="num">${num(s.rows)}</td><td class="small">${s.first ? esc(String(s.first).slice(0, 10)) : "—"}</td><td class="small">${s.last ? esc(String(s.last).slice(0, 10)) : "—"}</td><td class="small">${esc(s.timezone)}</td></tr>`).join("")}</tbody></table>
      <p class="small muted">Every timestamp is compared in UTC; the original value is shown beside it wherever it is cited.</p></div>${coverageCard(cov)}`;
}

const STATE_CLS = { runs: "b-completed", partly: "b-cannot_determine", "data ready, not built": "b-draft", "not built": "b-draft" };

/* The tag spec checked against the database: which checks have every tag they need, and what the source systems do not capture. */
function coverageCard(cov) {
  if (!cov) return "";
  const c = cov.counts, L = cov.labels;
  return `<div class="card"><h2>Evidence tags: what the system captures</h2>
    <p class="small muted">Each check needs certain facts on the records it reads (config/evidence_tags.yaml). This is that spec checked against the database: ${cov.build.runs} of ${cov.build.total} catalog checks run with every tag they need.
      ${Object.keys(L).map((k) => `<span class="tag">${esc(L[k])}: ${num(c[k])}</span>`).join(" ")}</p>
    ${cov.problems.length ? `<div class="err">${cov.problems.map(esc).join("<br>")}</div>` : ""}
    <table><thead><tr><th>Check</th><th>Name</th><th>Result</th><th>Tags missing in the source system</th></tr></thead><tbody>
      ${cov.checks.map((k) => `<tr><td class="mono">${esc(k.id)}</td><td>${esc(k.name)}</td><td><span class="badge ${STATE_CLS[k.state] || ""}">${esc(k.state)}</span></td><td class="small">${k.missing.length ? k.missing.map((m) => esc(m.name)).join("; ") : "<span class=muted>none</span>"}</td></tr>`).join("")}</tbody></table>
    <details><summary>${cov.not_captured.length} tags the source systems do not capture</summary><table><tbody>${cov.not_captured.map((t) => `<tr><td>${esc(t.name)}</td><td class="small muted">${esc(t.reason)}</td></tr>`).join("")}</tbody></table></details>
    <details><summary>${cov.not_needed.length} tags in the spec that are deliberately not stored</summary><table><tbody>${cov.not_needed.map((t) => `<tr><td>${esc(t.name)}</td><td class="small muted">${esc(t.reason)}</td></tr>`).join("")}</tbody></table></details></div>`;
}
