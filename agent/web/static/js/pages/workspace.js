import { app, state, api, esc, num, when, fdate, duration, badge, refresh } from "../core.js";
import { summary } from "./summary.js";
import { questionsTab } from "./questions.js";
import { findingsPage } from "./findings.js";
import { accountsTab, accountFile } from "./accounts.js";
import { letterTab } from "./letter.js";
import { packTab } from "./pack.js";
import { rulesPage } from "./rules.js";
import { agentTab, askTab } from "./agent.js";

const TABS = [["summary", "Summary"], ["questions", "Questions"], ["gaps", "Gap register"], ["followup", "Follow-up"], ["accounts", "Accounts"], ["letter", "Response letter"], ["pack", "Evidence pack"], ["agent", "Agent activity"], ["ask", "Ask the audit"], ["rules", "Rules & data"]];

export async function workspace(runId, tab, sub, q) {
  const d = await api(`/api/runs/${runId}`);
  const { run } = d, scale = run.severity_scale || [];
  const done = run.status === "completed";
  const activeTab = tab === "account" ? "accounts" : tab;
  const slaMin = state.config.sla_minutes || 120;
  app.innerHTML = `
    <p class="small no-print"><a href="#/">&larr; All audit requests</a></p>
    <div class="row between"><div><h1>${esc(run.request_id)} ${badge(run.status)}</h1>
      <div class="muted small">${run.lender ? `Requested by <strong>${esc(run.lender)}</strong> · ` : ""}${run.response_due ? `response due ${fdate(run.response_due)} · ` : ""}started ${when(run.started_at)}${run.finished_at ? ` · tested in ${duration(run.started_at, run.finished_at)} (target: under ${slaMin / 60} hours)` : ""}${run.created_by ? ` · by ${esc(run.created_by)}` : ""}</div></div></div>
    ${run.status === "failed" ? `<div class="err"><strong>The audit could not be completed.</strong> ${esc(run.notes || "")}</div>` : ""}
    ${run.status === "running" ? `<div class="card"><strong>Testing evidence…</strong> <span class="muted small">${d.tested_checks} of ${d.checks.length || "?"} checks done</span><div class="progress"><span style="width:${d.checks.length ? (d.tested_checks / d.checks.length) * 100 : 5}%"></span></div></div>` : ""}
    <div class="tabs no-print">${TABS.map(([k, l]) => `<a href="#/run/${runId}/${k}" class="${k === activeTab ? "active" : ""}">${l}${k === "gaps" && d.totals.gap ? ` <span class="tag">${num(d.totals.gap)}</span>` : ""}${k === "followup" && d.totals.cannot_determine ? ` <span class="tag">${num(d.totals.cannot_determine)}</span>` : ""}</a>`).join("")}</div>
    <div id="tab"></div>`;
  const el = document.getElementById("tab");
  const needDone = (fn) => (done ? fn() : (el.innerHTML = `<div class="note">This section is available once the audit has completed.</div>`));
  if (tab === "summary") summary(el, d, runId, scale);
  else if (tab === "questions" && sub) await findingsPage(el, d, runId, scale, { mode: "question", fixed: { question: sub }, base: `#/run/${runId}/questions/${encodeURIComponent(sub)}`, q, title: `Question ${sub}` });
  else if (tab === "questions") await needDone(() => questionsTab(el, d, runId, scale));
  else if (tab === "gaps") await findingsPage(el, d, runId, scale, { mode: "gaps", fixed: { status: "gap" }, base: `#/run/${runId}/gaps`, q });
  else if (tab === "followup") await findingsPage(el, d, runId, scale, { mode: "followup", fixed: { status: "cannot_determine" }, base: `#/run/${runId}/followup`, q });
  else if (tab === "accounts") await accountsTab(el, d, runId, q);
  else if (tab === "account") await accountFile(el, d, runId, scale, decodeURIComponent(sub || ""));
  else if (tab === "letter") await needDone(() => letterTab(el, d, runId));
  else if (tab === "pack") await needDone(() => packTab(el, d, runId));
  else if (tab === "agent") await agentTab(el, d, runId);
  else if (tab === "ask") await needDone(() => askTab(el, d, runId));
  else if (tab === "rules") await rulesPage(el, false, runId, done);
  if (run.status === "running") {
    state.poll = setInterval(async () => {
      const n = await api(`/api/runs/${runId}`).catch(() => null);
      if (n && (n.run.status !== "running" || n.tested_checks !== d.tested_checks)) refresh();
    }, 2500);
  }
}
