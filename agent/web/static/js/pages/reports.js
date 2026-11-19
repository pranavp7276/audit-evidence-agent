import { app, api, esc, num, when, badge, help } from "../core.js";

/* Reports: everything that can be handed over, per audit and across audits. PDF is the browser's own "save as PDF" from the page's print button. */

export async function reportsPage() {
  const runs = (await api("/api/runs")).filter((r) => r.status === "completed");
  app.innerHTML = `
    <h1>Reports ${help("response")}</h1>
    <p class="muted" style="max-width:72ch">What can be handed to a lender, a regulator or management. Open a report and use its Print / save as PDF button for a PDF.</p>
    <div class="card"><h2 style="margin-top:0">Each audit has</h2><ul class="rl">
      <li><strong>Summary</strong> <span class="muted small">results, acceptance criteria and the traps caught</span></li>
      <li><strong>Lender brief</strong> <span class="muted small">one page for the relationship manager</span></li>
      <li><strong>Response letter</strong> <span class="muted small">every statement referenced and checked</span></li>
      <li><strong>Evidence pack</strong> <span class="muted small">index, extracts, gap report, agent trace (zip)</span></li></ul></div>
    <div class="card" style="padding:0"><table><thead><tr><th>Audit</th><th>Status</th><th class="num">Gaps</th><th>Reports</th></tr></thead><tbody>
    ${runs.map((r) => `<tr><td><strong>${esc(r.request_id)}</strong><div class="small muted">${esc(r.lender || "")} ${when(r.started_at)}</div></td><td>${badge(r.letter_status || "completed")}</td><td class="num">${num(r.gaps)}</td>
      <td class="small"><a href="#/run/${r.run_id}/summary">Summary</a> · <a href="#/run/${r.run_id}/brief">Lender brief</a> · <a href="#/run/${r.run_id}/letter">Response letter</a> · <a href="/api/runs/${r.run_id}/pack.zip">Evidence pack</a> · <a href="/api/runs/${r.run_id}/files/gap_report.csv">Gap report (CSV)</a> · <a href="/api/runs/${r.run_id}/files/agent_trace.csv">Agent trace (CSV)</a></td></tr>`).join("")
      || `<tr><td colspan="4"><div class="empty">No completed audits yet.</div></td></tr>`}</tbody></table></div>`;
}
