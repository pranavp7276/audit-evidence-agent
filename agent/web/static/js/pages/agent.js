import { api, post, esc, stat } from "../core.js";

const STATUS = { retry: "b-cannot_determine", resolved: "b-evidenced", unresolved: "b-cannot_determine", failed: "b-failed" };
const STATUS_TEXT = { retry: "Retry", resolved: "Resolved", unresolved: "Unresolved", failed: "Failed" };

export async function agentTab(el, d, runId) {
  const [t, tools] = await Promise.all([api(`/api/runs/${runId}/agent`), api("/api/agent/tools")]);
  const s = t.summary;
  if (!t.recorded) {
    el.innerHTML = `<div class="note">The agent's activity was not recorded for this audit (it was run before activity logging existed).</div>`;
    return;
  }
  const row = (x) => `<tr><td class="num">${x.seq}</td><td>${esc(x.agent)}</td><td>${esc(x.action)}${x.check_id ? ` <span class="tag">${esc(x.check_id)}</span>` : ""}</td>
    <td class="mono small">${esc(x.tool || "")}</td><td>${STATUS_TEXT[x.status] ? `<span class="badge ${STATUS[x.status]}">${STATUS_TEXT[x.status]}</span>` : ""}</td><td class="num">${x.duration_ms == null ? "" : (x.duration_ms / 1000).toFixed(1) + " s"}</td></tr>`;
  el.innerHTML = `
    <p class="muted">The agent works in a fixed order: plan, retrieve and evaluate, investigate, report. Each step it took is listed here. It decides nothing by judgement: results come from the checks' rules, and the investigator only searches more places for evidence. <a href="#/guide/agent">How the agent works</a></p>
    <div class="grid cols4">${stat(s.steps, "steps recorded")}${stat(s.tool_calls, "tool requests")}${stat(s.resolved, "missing evidence found elsewhere", "ok")}${stat(s.unresolved, "still unresolved, queued for follow-up", "unk")}</div>
    <div class="card" style="margin-top:16px"><h2 style="margin-top:0">Steps</h2>
      <div class="row no-print" style="margin-bottom:8px">${[["all", "All"], ...t.phases.map((p) => [p.key, `${p.label} (${p.steps})`])].map(([k, l]) => `<button class="phase-btn ${k === "all" ? "primary" : ""}" data-p="${k}">${esc(l)}</button>`).join("")}</div>
      <table><thead><tr><th class="num">#</th><th>Agent</th><th>What it did</th><th>Tool</th><th>Outcome</th><th class="num">Time</th></tr></thead><tbody id="steps">${t.steps.map(row).join("")}</tbody></table></div>
    <details class="card"><summary style="margin:0">Tools the agent can call (${tools.length}, all read-only)</summary>
      <table style="margin-top:10px"><thead><tr><th>Tool</th><th>What it does</th><th>Source</th></tr></thead><tbody>${tools.map((x) => `<tr><td class="mono">${esc(x.name)}</td><td>${esc(x.description)}</td><td>${esc(x.sources.join(", "))}</td></tr>`).join("")}</tbody></table></details>`;
  el.querySelectorAll(".phase-btn").forEach((b) => b.addEventListener("click", () => {
    el.querySelectorAll(".phase-btn").forEach((x) => x.classList.toggle("primary", x === b));
    el.querySelector("#steps").innerHTML = (b.dataset.p === "all" ? t.steps : t.steps.filter((x) => x.phase === b.dataset.p)).map(row).join("");
  }));
}

export function askTab(el, d, runId) {
  const examples = ["Which accounts have the most gaps?", "How many critical gaps are there per question?", "List the cannot-determine findings for Q4"];
  el.innerHTML = `<div class="card"><h2 style="margin-top:0">Ask about this audit</h2>
    <p class="muted small">Answers come only from this audit's findings. If an answer names findings, the numbers link to them. Nothing is changed or re-tested here.</p>
    <div class="row"><input id="q" type="text" style="flex:1;min-width:260px" maxlength="500" placeholder="Ask a question about the results"><button id="go" class="primary">Ask</button></div>
    <p class="small muted" style="margin-bottom:0">Try: ${examples.map((x) => `<a href="#" class="ex">${esc(x)}</a>`).join(" · ")}</p><div id="out"></div></div>`;
  const out = el.querySelector("#out"), q = el.querySelector("#q");
  const go = async () => {
    const text = q.value.trim();
    if (!text) return;
    out.innerHTML = `<p class="muted">Looking through the findings…</p>`;
    try {
      const r = await post(`/api/runs/${runId}/ask`, { question: text });
      out.innerHTML = `<div class="card" style="margin:12px 0 0"><div style="white-space:pre-wrap">${esc(r.answer)}</div>
        ${r.finding_ids.length ? `<p class="small" style="margin-bottom:0">Findings: ${r.finding_ids.map((i) => `<a href="#/run/${runId}/gaps?q=${i}">#${i}</a>`).join(", ")}</p>` : ""}
        <p class="small muted" style="margin-bottom:0">${r.used_model ? "Answered by the model from the query results." : "Model unavailable: matching findings listed."} ${r.steps.length} step(s).</p></div>`;
    } catch (e) { out.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  el.querySelector("#go").onclick = go;
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") go(); });
  el.querySelectorAll(".ex").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); q.value = a.textContent; go(); }));
}
