import { api, esc, num, fdate, badge, navigate, refresh } from "../core.js";
import { evidenceMap, wireEvidenceMap } from "./evidence_map.js";
import { findingItem, wireFindings } from "./findings.js";

const SOURCE_TABLE = { call: "cn_core.tele_process_instance_call_logs", whatsapp: "cn_core.communication_dashboard_t", sms: "cn_core.communication_dashboard_t",
  consent: "compliance.customer_consent", recording: "compliance.call_recording", notice: "compliance.notice" };

export async function accountsTab(el, d, runId, q) {
  const page = +(q.page || 0), size = 50, only = q.gaps === "1";
  const data = await api(`/api/runs/${runId}/accounts?${new URLSearchParams({ q: q.q || "", only_gaps: only, limit: size, offset: page * size })}`);
  const link = (over) => `#/run/${runId}/accounts?` + new URLSearchParams(Object.entries({ ...q, ...over }).filter(([, v]) => v !== "" && v != null)).toString();
  const unresolved = (d.coverage && d.coverage.unresolved) || [];
  el.innerHTML = `${unresolved.length ? `<div class="card"><h2>Account references not tested (${unresolved.length})</h2>
      <p class="muted small">These references from the request matched no loan account, or matched more than one. They are kept here and are not tested until Compliance resolves them.</p>
      <table><thead><tr><th>Reference as written</th><th>Status</th><th>Detail</th></tr></thead><tbody>${unresolved.map((u) => `<tr><td class="mono">${esc(u.ref)}</td><td><span class="badge b-${u.status === "ambiguous" ? "cannot_determine" : "gap"}">${esc(u.status)}</span></td><td class="small">${esc(u.note || "")}</td></tr>`).join("")}</tbody></table></div>` : ""}
    <h2>Sampled accounts</h2><p class="muted small">Open an account to see every record involved on one timeline, with the events behind each finding highlighted.</p>
    <div class="card no-print"><form id="af" class="row"><div style="flex:1;min-width:180px"><label>Loan account contains</label><input type="search" name="q" value="${esc(q.q || "")}" placeholder="CNF123456789"></div>
      <label style="align-self:flex-end;font-weight:400"><input type="checkbox" name="gaps" value="1" style="width:auto" ${only ? "checked" : ""}> Only accounts with gaps</label><div style="align-self:flex-end"><button class="primary">Search</button></div></form></div>
    <div class="card"><p class="muted small">${num(data.total)} account${data.total === 1 ? "" : "s"}</p>
    <table><thead><tr><th>Loan account</th><th class="num">Gaps</th><th class="num">Cannot determine</th><th class="num">Evidenced</th><th>Questions with gaps</th></tr></thead><tbody>
    ${data.rows.map((r) => `<tr class="click" data-acct="${esc(r.account_id)}"><td class="mono"><strong>${esc(r.account_number || r.account_id)}</strong><div class="small muted">CN id ${esc(r.account_id)}</div></td><td class="num"><strong style="color:${+r.gaps ? "var(--gap)" : "inherit"}">${num(r.gaps)}</strong></td><td class="num">${num(r.cannot_determine)}</td><td class="num">${num(r.evidenced)}</td><td>${(r.gap_questions || []).map((x) => `<span class="tag">${esc(x)}</span>`).join(" ")}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No accounts match.</td></tr>`}
    </tbody></table><div class="pager">${page > 0 ? `<a class="btn" href="${link({ page: page - 1 })}">&larr; Previous</a>` : ""}${(page + 1) * size < data.total ? `<a class="btn" href="${link({ page: page + 1 })}">Next &rarr;</a>` : ""}</div></div>`;
  el.querySelectorAll("tr[data-acct]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/run/${runId}/account/${encodeURIComponent(tr.dataset.acct)}`)));
  el.querySelector("#af").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    navigate(`#/run/${runId}/accounts?` + new URLSearchParams([...fd.entries()].filter(([, v]) => v)).toString());
  });
}

export async function accountFile(el, d, runId, scale, account) {
  const a = await api(`/api/runs/${runId}/accounts/${encodeURIComponent(account)}`);
  a.findings.forEach((f) => (f.run_id = runId));
  const reviewable = d.run.status === "completed";
  const byCheck = {};
  a.findings.forEach((f) => { const c = (byCheck[f.check_id] ||= { f, status: "evidenced", n: 0 }); c.n++; if (f.status === "gap") c.status = "gap"; else if (f.status === "cannot_determine" && c.status !== "gap") c.status = "cannot_determine"; });
  let lastDay = "";
  const tl = a.events.map((e) => {
    const day = e.ts.slice(0, 10), head = day !== lastDay ? `<div class="day">${fdate(day)}</div>` : ""; lastDay = day;
    const t = SOURCE_TABLE[e.kind];
    return `${head}<div class="ev k-${esc(e.kind)} ${e.flag === "gap" ? "f-gap" : e.flag === "cannot_determine" ? "f-cannot_determine" : ""}">
      <div class="t"><strong>${esc(e.title)}</strong>${e.flag ? badge(e.flag) : ""}<span class="time">${e.all_day ? "date only" : e.ts.slice(11, 19) + " UTC"}</span><span class="small muted">source: ${esc(e.src_ts)} ${e.tz === "date" ? "" : `(${esc(e.tz)})`}</span></div>
      <div class="small muted">${esc(e.source)} · ${esc(e.detail)} · <button class="link small" data-table="${t}" data-rec="${esc(e.id)}">${esc(e.id)}</button></div></div>`;
  }).join("");
  el.innerHTML = `<p class="small no-print"><a href="#/run/${runId}/accounts">&larr; All accounts</a></p>
    <h2>Loan account <span class="mono">${esc(a.account_number || account)}</span> <span class="small muted">· CN id ${esc(account)}${a.institution_code ? ` · ${esc(a.institution_code)}` : ""}</span></h2>
    <div class="card"><h3 style="margin-top:0">Result by check</h3><div class="row">${d.checks.map((c) => { const r = byCheck[c.check_id]; return `<div class="stat" style="min-width:150px"><div class="small muted">${esc(c.check_id)} · ${esc(c.title)}</div><div style="margin-top:4px">${r ? badge(r.status) : `<span class="muted small">no result</span>`}</div></div>`; }).join("")}</div></div>
    ${evidenceMap(a.events, a.findings)}
    <div class="grid cols2" style="grid-template-columns:1.1fr 1fr;align-items:start">
      <div class="card"><h3 style="margin-top:0">Timeline (all times in UTC; source time shown beside it)</h3>${a.events.length ? `<div class="tl">${tl}</div>` : `<div class="empty">No records for this account in any source.</div>`}
        <p class="small muted">Highlighted events are cited by a finding: red for a gap, amber for cannot determine.</p></div>
      <div><h3 style="margin-top:0">Findings</h3><div id="list">${a.findings.map((f) => findingItem(f, scale, reviewable, false)).join("") || `<div class="empty">No findings for this account.</div>`}</div></div></div>`;
  wireFindings(el, runId, refresh);
  wireEvidenceMap(el);
}
