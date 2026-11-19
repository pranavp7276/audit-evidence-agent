import { app, state, api, post, esc, when, fdate, help, sevBadge, needName, refresh, rulebookNav } from "../core.js";

const WEIGHT_HELP = { 1: "Normal review order", 2: "Elevated: reviewed earlier", 3: "Highest priority: reviewed first" };
export async function guardrailsPage(q) {
  const [list, docs] = await Promise.all([api("/api/guardrails"), api("/api/kb")]);
  const tab = q.show || "all";
  const shown = list.filter((g) => tab === "all" || g.status === tab);
  app.innerHTML = `${rulebookNav("#/guardrails")}<div class="row between"><div><h1>Guardrails ${help("guardrails")}</h1>
      <p class="muted">What the audit tests, how serious a failure is, and how reviewers should order their work. Each change is a new version; an audit records the version it applied.</p></div>
      <button class="primary" id="newg">New guardrail</button></div>
    <div class="card"><div class="grid cols3" style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px">
      <div><strong>Outcome</strong><div class="small muted">Evidenced, gap or cannot determine. Decided only by the evidence and the test.</div></div>
      <div><strong>Severity</strong><div class="small muted">How serious a confirmed gap is. The audit request's own scale wins; otherwise the guardrail's default.</div></div>
      <div><strong>Priority weight (1 to 3)</strong><div class="small muted">Which controls reviewers look at first. It never hides or changes a gap, and a weight above 1 needs a recorded reason.</div></div></div></div>
    <div class="tabs">${[["all", "All"], ["published", "Published"], ["draft", "Drafts"], ["retired", "Retired"]].map(([k, l]) => `<a href="#/guardrails?show=${k}" class="${k === tab ? "active" : ""}">${l} <span class="tag">${list.filter((g) => k === "all" || g.status === k).length}</span></a>`).join("")}</div>
    <div class="card">${shown.length ? `<table><thead><tr><th>Guardrail</th><th>Severity</th><th>Weight</th><th>Source</th><th>Effective</th><th>Status</th><th></th></tr></thead><tbody>
      ${shown.map((g) => `<tr><td><strong>${esc(g.title)}</strong><div class="small muted">${esc(g.check_type.replace(/_/g, " "))} · v${g.version}${g.versions > 1 ? ` (${g.versions} versions)` : ""}</div></td>
        <td>${sevBadge(g.default_severity, ["Critical", "Major", "Minor"])}</td><td><span class="tag" title="${esc(g.weight_reason || WEIGHT_HELP[g.priority_weight])}">${g.priority_weight}</span></td>
        <td class="small">${g.source_doc_id ? `<a href="#/kb/${g.source_doc_id}">${esc(g.source_doc_title)}</a>${g.source_clause ? ` · clause ${esc(g.source_clause)}` : ""}` : esc(g.source_label || "—")}</td>
        <td class="small">${fdate(g.effective_from)}</td><td><span class="badge b-${g.status === "published" ? "completed" : g.status === "draft" ? "draft" : "open"}">${esc(g.status)}</span></td>
        <td><button class="link" data-edit="${g.guardrail_id}">Edit</button></td></tr>`).join("")}</tbody></table>` : `<div class="empty">Nothing here yet.</div>`}</div>`;
  const byId = Object.fromEntries(list.map((g) => [g.guardrail_id, g]));
  app.querySelectorAll("[data-edit]").forEach((b) => b.addEventListener("click", () => guardrailForm(byId[b.dataset.edit], docs)));
  document.getElementById("newg").onclick = () => guardrailForm(null, docs);
  if (q.edit && byId[q.edit]) guardrailForm(byId[q.edit], docs);
}

async function guardrailForm(g, docs) {
  const m = document.getElementById("modal");
  const types = state.config.check_types || {};
  const v = g || { check_type: "consent_before_contact", title: "", obligation: "", default_severity: "Critical", priority_weight: 1, effective_from: new Date().toISOString().slice(0, 10), status: "draft", parameters: {}, applicability: {} };
  const hist = g ? await api(`/api/guardrails/${g.guardrail_id}/versions`) : [];
  m.hidden = false;
  m.innerHTML = `<div class="box" style="max-width:720px"><div class="row between"><h2 style="margin:0">${g ? "Edit guardrail (saves a new version)" : "New guardrail"}</h2><button id="gclose">Close</button></div>
    <form id="gf" style="margin-top:12px">
      <label>Title</label><input type="text" name="title" value="${esc(v.title)}" required>
      <label style="margin-top:10px">Obligation (what must hold)</label><textarea name="obligation" style="min-height:90px;font-family:inherit">${esc(v.obligation)}</textarea>
      <div class="grid cols2" style="margin-top:10px">
        <div><label>Control tested</label><select name="check_type" ${g ? "disabled" : ""}>${Object.entries(types).filter(([k]) => k !== "other").map(([k, t]) => `<option value="${k}" ${k === v.check_type ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>
        <div><label>Default severity</label><select name="default_severity">${["Critical", "Major", "Minor"].map((x) => `<option ${x === v.default_severity ? "selected" : ""}>${x}</option>`).join("")}</select></div>
        <div><label>Priority weight</label><select name="priority_weight">${[1, 2, 3].map((w) => `<option value="${w}" ${w === v.priority_weight ? "selected" : ""}>${w} · ${WEIGHT_HELP[w]}</option>`).join("")}</select></div>
        <div><label>Effective from</label><input type="date" name="effective_from" value="${esc(String(v.effective_from).slice(0, 10))}"></div>
        <div><label>Source document</label><select name="source_doc_id"><option value="">(none)</option>${docs.map((d) => `<option value="${d.doc_id}" ${d.doc_id === v.source_doc_id ? "selected" : ""}>${esc(d.title)}</option>`).join("")}</select></div>
        <div><label>Clause or page</label><input type="text" name="source_clause" value="${esc(v.source_clause || "")}"></div></div>
      <label style="margin-top:10px">Reason for the weight (required above 1)</label><input type="text" name="weight_reason" value="${esc(v.weight_reason || "")}" placeholder="e.g. regulator flagged this control in the last inspection">
      <label style="margin-top:10px">Required evidence</label><input type="text" name="required_evidence" value="${esc(v.required_evidence || "")}">
      <label style="margin-top:10px">Limits stated in the source (for reference; tests read the D12 rules)</label><input type="text" name="parameters" value="${esc(JSON.stringify(v.parameters || {}))}" class="mono">
      <div class="grid cols2" style="margin-top:10px"><div><label>Status</label><select name="status">${["draft", "published", "retired"].map((x) => `<option ${x === v.status ? "selected" : ""}>${x}</option>`).join("")}</select></div></div>
      <div class="row" style="margin-top:14px"><button class="primary">${g ? "Save as new version" : "Create guardrail"}</button><span id="gerr"></span></div></form>
    ${hist.length ? `<h3>Version history</h3><table><thead><tr><th>v</th><th>Status</th><th>Severity</th><th>Weight</th><th>Effective</th><th>By</th></tr></thead><tbody>${hist.map((h) => `<tr><td>${h.version}</td><td>${esc(h.status)}</td><td>${esc(h.default_severity)}</td><td>${h.priority_weight}${h.weight_reason ? ` <span class="small muted">(${esc(h.weight_reason)})</span>` : ""}</td><td class="small">${fdate(h.effective_from)}</td><td class="small">${esc(h.created_by)} · ${when(h.created_at)}</td></tr>`).join("")}</tbody></table>` : ""}</div>`;
  m.onclick = (e) => { if (e.target === m) m.hidden = true; };
  document.getElementById("gclose").onclick = () => (m.hidden = true);
  document.getElementById("gf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const who = needName(); if (!who) return;
    const f = Object.fromEntries(new FormData(ev.target).entries());
    let params = {};
    try { params = JSON.parse(f.parameters || "{}"); } catch (_) { document.getElementById("gerr").innerHTML = `<span class="badge b-failed">Limits must be valid JSON, e.g. {"max_per_day": 5}</span>`; return; }
    const body = { ...f, check_type: g ? g.check_type : f.check_type, parameters: params, applicability: v.applicability || {}, source_label: v.source_label || null,
      source_doc_id: f.source_doc_id ? +f.source_doc_id : null, priority_weight: +f.priority_weight, created_by: who };
    try { await post(g ? `/api/guardrails/${g.guardrail_id}/versions` : "/api/guardrails", body); m.hidden = true; refresh(); }
    catch (e) { document.getElementById("gerr").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  });
}
