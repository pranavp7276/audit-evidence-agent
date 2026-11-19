import { app, api, post, esc, fdate, navigate, needName, refresh } from "../core.js";

/* The audit plan: which audits and readiness checks are expected, who owns them, and when they are due. The year view is the plan by month. */

const STATUS = { planned: "Planned", in_progress: "In progress", done: "Done", cancelled: "Cancelled" };
const CLS = { planned: "b-draft", in_progress: "b-in_review", done: "b-completed", cancelled: "b-draft" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
let year = new Date().getFullYear();

export async function planPage(q) {
  if (q.year) year = +q.year;
  const { rows } = await api("/api/plan");
  const when = (p) => String(p.due_date || p.planned_start || "").slice(0, 10);
  const byMonth = (m) => rows.filter((p) => when(p).startsWith(`${year}-${String(m + 1).padStart(2, "0")}`));
  const undated = rows.filter((p) => !when(p));
  app.innerHTML = `
    <div class="row between"><div><h1>Audit plan</h1><p class="muted" style="max-width:70ch">The audits and readiness checks you expect, who owns each, and when it is due. Start one from here and the audit is linked back to its plan entry; a recurring entry schedules the next one.</p></div>
      <button class="primary big" id="newp">Plan an audit</button></div>
    <div id="form" class="card" hidden><h3 style="margin-top:0">Plan an audit</h3>
      <div class="grid cols2"><div><label for="pt">Title</label><input id="pt" type="text" placeholder="e.g. FY27 half-year outsourced collections audit"></div><div><label for="pl">Lender or regulator</label><input id="pl" type="text"></div></div>
      <div class="grid cols4" style="grid-template-columns:repeat(4,minmax(0,1fr));margin-top:8px"><div><label for="pk">Kind</label><select id="pk"><option value="audit">Audit for a request</option><option value="readiness">Readiness check</option></select></div>
        <div><label for="ps">Planned start</label><input id="ps" type="date"></div><div><label for="pd">Due</label><input id="pd" type="date"></div><div><label for="pr">Repeats</label><select id="pr"><option value="none">Does not repeat</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></div></div>
      <div class="grid cols2" style="margin-top:8px"><div><label for="po">Owner</label><input id="po" type="text"></div><div><label for="px">Scope</label><input id="px" type="text" placeholder="Optional: what the audit covers"></div></div>
      <div class="row" style="margin-top:10px"><button class="primary" id="savep">Add to the plan</button><span id="pe"></span></div></div>
    <div class="row between" style="margin-top:14px"><h2 style="margin:0">${year}</h2><div class="row"><a class="btn" href="#/plan?year=${year - 1}">&larr; ${year - 1}</a><a class="btn" href="#/plan?year=${year + 1}">${year + 1} &rarr;</a></div></div>
    <div class="year">${MONTHS.map((m, i) => `<div class="mon"><div class="mn">${m}</div>${byMonth(i).map((p) => `<a class="pe ${CLS[p.status]} ${p.overdue ? "late" : ""}" href="#plan-${p.plan_id}" title="${esc(p.title)}: ${STATUS[p.status]}">${esc(p.title)}</a>`).join("") || `<span class="muted small">—</span>`}</div>`).join("")}</div>
    <div class="card" style="padding:0;margin-top:14px"><table><thead><tr><th>Planned audit</th><th>Kind</th><th>Start</th><th>Due</th><th>Owner</th><th>Status</th><th></th></tr></thead><tbody>
    ${rows.map((p) => `<tr id="plan-${p.plan_id}"><td><strong>${esc(p.title)}</strong><div class="small muted">${esc(p.lender || "")}${p.scope ? ` · ${esc(p.scope)}` : ""}${p.recurrence !== "none" ? ` · repeats ${esc(p.recurrence)}` : ""}</div></td>
      <td class="small">${p.kind === "readiness" ? "Readiness check" : "Audit"}</td><td class="small">${p.planned_start ? fdate(p.planned_start) : "—"}</td>
      <td class="small">${p.due_date ? fdate(p.due_date) : "—"}${p.overdue ? ` <span class="badge b-failed">overdue</span>` : ""}</td><td class="small">${esc(p.owner || "—")}</td>
      <td><select data-st="${p.plan_id}" style="width:auto">${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k === p.status ? "selected" : ""}>${v}</option>`).join("")}</select></td>
      <td class="small">${p.run_id ? `<a href="#/run/${p.run_id}">Open ${esc(p.request_id || "audit")}</a>` : p.status === "planned" || p.status === "in_progress" ? `<button class="link" data-start="${p.plan_id}" data-kind="${p.kind}">${p.kind === "readiness" ? "Run now" : "Start audit"}</button>` : ""}</td></tr>`).join("")
      || `<tr><td colspan="7"><div class="empty">Nothing planned yet. Add the audits you expect, so due dates show up on the dashboard and in alerts.</div></td></tr>`}
    </tbody></table></div>${undated.length ? `<p class="small muted">${undated.length} entr${undated.length === 1 ? "y has" : "ies have"} no dates and are not on the year view.</p>` : ""}`;
  const form = app.querySelector("#form");
  app.querySelector("#newp").onclick = () => { form.hidden = !form.hidden; };
  app.querySelector("#savep").onclick = async () => {
    const who = needName(); if (!who) return;
    const v = (id) => app.querySelector(id).value;
    try { await post("/api/plan", { title: v("#pt"), lender: v("#pl"), kind: v("#pk"), planned_start: v("#ps"), due_date: v("#pd"), recurrence: v("#pr"), owner: v("#po"), scope: v("#px"), actor: who }); refresh(); }
    catch (e) { app.querySelector("#pe").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  };
  app.querySelectorAll("[data-st]").forEach((s) => s.addEventListener("change", async () => { await post(`/api/plan/${s.dataset.st}/status`, { status: s.value }); refresh(); }));
  app.querySelectorAll("[data-start]").forEach((b) => b.addEventListener("click", async () => {
    if (b.dataset.kind === "audit") { navigate(`#/new?plan=${b.dataset.start}`); return; }
    const who = needName(); if (!who) return;
    try { const r = await post("/api/readiness", { requested_by: who, size: 1000 }); await post(`/api/plan/${b.dataset.start}/status`, { status: "in_progress" }); navigate(`#/run/${r.run_id}`); }
    catch (e) { alert(e.message); }
  }));
}
