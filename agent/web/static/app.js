"use strict";
const app = document.getElementById("app");
const state = { poll: null, config: {} };

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => Number(n || 0).toLocaleString();
const when = (s) => (s ? new Date(s).toLocaleString() : "");

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw new Error(msg);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}

function badge(status) {
  return `<span class="badge b-${esc(status)}">${esc(String(status).replace("_", " "))}</span>`;
}
function sevBadge(label, scale) {
  if (!label) return "";
  const i = Math.min(Math.max(scale.indexOf(label), 0), 3);
  return `<span class="badge sev sev-${i}">${esc(label)}</span>`;
}
function stackBar(e, g, u) {
  const t = (e + g + u) || 1;
  return `<div class="bar" title="${e} evidenced, ${g} gap, ${u} cannot determine">
    <span class="e" style="width:${(e / t) * 100}%"></span><span class="g" style="width:${(g / t) * 100}%"></span><span class="u" style="width:${(u / t) * 100}%"></span></div>`;
}
function stat(n, label, cls = "") { return `<div class="stat ${cls}"><div class="n">${num(n)}</div><div class="l">${esc(label)}</div></div>`; }

/* ---------- tiny markdown renderer (headings, lists, tables, bold/italic/code) ---------- */
function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/_([^_]+)_/g, "<em>$1</em>").replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
}
function markdown(md) {
  const out = []; let list = false, table = [];
  const flushTable = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|\s*-/.test(r)).map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    out.push("<table><thead><tr>" + rows[0].map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>" +
      rows.slice(1).map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table>");
    table = [];
  };
  for (const line of md.split("\n")) {
    if (line.startsWith("|")) { table.push(line); continue; }
    flushTable();
    if (/^- /.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(line.slice(2))}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    const h = line.match(/^(#{1,3}) (.*)/);
    if (h) out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  flushTable(); if (list) out.push("</ul>");
  return out.join("\n");
}

/* ---------- routing ---------- */
function stopPolling() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
function parseHash() {
  const [path, query = ""] = location.hash.slice(1).split("?");
  return { parts: path.split("/").filter(Boolean), q: Object.fromEntries(new URLSearchParams(query)) };
}
async function route() {
  stopPolling();
  const { parts, q } = parseHash();
  const section = parts[0] === "sql" ? "sql" : "runs";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === section));
  try {
    if (parts[0] === "sql") await sqlPage();
    else if (parts[0] === "run" && parts[1]) await runPage(parts[1], parts[2] || "overview", q);
    else await homePage();
  } catch (e) {
    app.innerHTML = `<div class="err">${esc(e.message)}</div><p><a href="#/">Back to audit runs</a></p>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

/* ---------- home: new run + history ---------- */
async function homePage() {
  const [runs, examples] = await Promise.all([api("/api/runs"), api("/api/examples")]);
  app.innerHTML = `
    <h1>Audit runs</h1>
    <p class="muted">Upload an audit request. The agent splits it into checks, tests the evidence for each sampled account, and returns a cited evidence pack, a gap report and a draft response.</p>
    <div class="card">
      <h2>New audit run</h2>
      <form id="new-run">
        <div class="grid cols2">
          <div><label for="rid">Request id</label><input id="rid" type="text" value="CO-04" required></div>
          <div><label for="file">Request file (PDF, .eml or text)</label><input id="file" type="file" accept=".pdf,.eml,.txt,.md"></div>
        </div>
        <div style="margin-top:12px">
          <div class="row between"><label for="text">…or paste the request text</label>
            ${examples.length ? `<span class="small muted">Example: ${examples.map((n) => `<button type="button" class="link" data-example="${esc(n)}">${esc(n)}</button>`).join(" · ")}</span>` : ""}</div>
          <textarea id="text" placeholder="Q1. ... Q2. ...&#10;Severity scale ...&#10;Sampled accounts: ..."></textarea>
        </div>
        <details><summary>Sample options (only if the request does not list its accounts)</summary>
          <div class="grid cols2">
            <div><label for="accts">Account ids (comma separated)</label><input id="accts" type="text" placeholder="ACC00001, ACC00002"></div>
            <div><label for="rn">…or a random sample of</label><input id="rn" type="number" min="1" max="2000" placeholder="300"></div>
          </div>
        </details>
        <div class="row" style="margin-top:14px"><button class="primary" id="start">Run audit</button><span id="form-err"></span></div>
      </form>
    </div>
    <div class="card">
      <h2>History</h2>
      ${runs.length ? `<table><thead><tr><th>Request</th><th>Status</th><th class="num">Accounts</th><th class="num">Checks</th><th>Results</th><th class="num">Gaps</th><th>Started</th></tr></thead><tbody>
        ${runs.map((r) => `<tr class="click" data-run="${r.run_id}"><td><strong>${esc(r.request_id)}</strong><div class="small muted mono">${r.run_id.slice(0, 8)}</div></td>
          <td>${badge(r.status)}</td><td class="num">${num(r.accounts)}</td><td class="num">${num(r.checks)}</td>
          <td>${stackBar(+r.evidenced, +r.gaps, +r.cannot_determine)}</td><td class="num">${num(r.gaps)}</td><td class="small">${when(r.started_at)}</td></tr>`).join("")}
        </tbody></table>` : `<div class="empty">No runs yet. Start one above.</div>`}
    </div>`;
  app.querySelectorAll("tr[data-run]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${tr.dataset.run}`)));
  app.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", async () => {
    const ex = await api("/api/examples/" + encodeURIComponent(b.dataset.example));
    document.getElementById("text").value = ex.text;
    document.getElementById("rid").value = ex.name.replace(/\.[^.]+$/, "");
  }));
  document.getElementById("new-run").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData();
    fd.append("request_id", document.getElementById("rid").value);
    fd.append("text", document.getElementById("text").value);
    fd.append("accounts", document.getElementById("accts").value);
    if (document.getElementById("rn").value) fd.append("random_n", document.getElementById("rn").value);
    const f = document.getElementById("file").files[0];
    if (f) fd.append("file", f);
    const btn = document.getElementById("start"); btn.disabled = true; btn.textContent = "Starting…";
    try {
      const r = await api("/api/runs", { method: "POST", body: fd });
      location.hash = `#/run/${r.run_id}`;
    } catch (e) {
      document.getElementById("form-err").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`;
      btn.disabled = false; btn.textContent = "Run audit";
    }
  });
}

/* ---------- run page ---------- */
const TABS = [["overview", "Overview"], ["findings", "Findings"], ["gaps", "Gap report"], ["letter", "Response letter"], ["pack", "Evidence pack"], ["score", "Score"]];

async function runPage(runId, tab, q) {
  const d = await api(`/api/runs/${runId}`);
  const { run, checks } = d;
  const scale = run.severity_scale || [];
  const done = run.status !== "running";
  const header = `
    <p class="small"><a href="#/">&larr; All runs</a></p>
    <div class="row between"><div><h1>${esc(run.request_id)} ${badge(run.status)}</h1>
      <div class="muted small">Run <span class="mono">${run.run_id}</span> · started ${when(run.started_at)}${run.finished_at ? ` · finished ${when(run.finished_at)}` : ""} · ${esc(run.request_source)} request</div></div></div>
    ${run.status === "failed" ? `<div class="err"><strong>The run failed.</strong> ${esc(run.notes || "")}</div>` : ""}
    ${run.status === "running" ? `<div class="card"><strong>Testing evidence…</strong> <span class="muted small">${d.tested_checks} of ${checks.length || "?"} checks done</span>
      <div class="progress"><span style="width:${checks.length ? (d.tested_checks / checks.length) * 100 : 5}%"></span></div></div>` : ""}
    <div class="tabs">${TABS.map(([k, l]) => `<a href="#/run/${runId}/${k}" class="${k === tab ? "active" : ""}">${l}</a>`).join("")}</div>
    <div id="tab"></div>`;
  app.innerHTML = header;
  const el = document.getElementById("tab");
  if (tab === "overview") overview(el, d, runId, scale);
  else if (tab === "findings") await findingsTab(el, d, runId, scale, q, false);
  else if (tab === "gaps") await findingsTab(el, d, runId, scale, q, true);
  else if (tab === "letter") await letterTab(el, runId, done);
  else if (tab === "pack") await packTab(el, runId, done);
  else if (tab === "score") scoreTab(el, runId, done);
  if (run.status === "running") {
    state.poll = setInterval(async () => {
      const n = await api(`/api/runs/${runId}`).catch(() => null);
      if (n && (n.run.status !== "running" || n.tested_checks !== d.tested_checks)) route();
    }, 2500);
  }
}

function overview(el, d, runId, scale) {
  const { checks, totals, severity } = d;
  const maxSev = Math.max(1, ...severity.map((s) => +s.findings));
  el.innerHTML = `
    <div class="grid cols4">${stat(checks.length, "checks from the request")}${stat(totals.evidenced, "evidenced", "ok")}${stat(totals.gap, "gap findings", "gap")}${stat(totals.cannot_determine, "cannot determine", "unk")}</div>
    <div class="grid cols2" style="margin-top:14px">
      <div class="card"><h2>Gaps by severity</h2>
        ${severity.length ? severity.map((s, i) => `<div style="margin-bottom:12px"><div class="row between small"><span>${sevBadge(s.severity, scale)}</span><span><strong>${num(s.findings)}</strong> findings · ${num(s.accounts)} accounts</span></div>
          <div class="hbar"><span style="width:${(s.findings / maxSev) * 100}%;background:var(--sev-${Math.min(scale.indexOf(s.severity), 2) < 0 ? 2 : Math.min(scale.indexOf(s.severity), 2)})"></span></div></div>`).join("") : `<div class="empty">${d.run.status === "running" ? "Waiting for results…" : "No gaps found."}</div>`}
        <div class="small muted">Severity scale as given in the request: ${scale.length ? scale.map(esc).join(" › ") : "none given (gaps are graded at the most severe level)"}.</div></div>
      <div class="card"><h2>Accounts with gaps</h2><div class="stat gap" style="border:0;padding:0"><div class="n">${num(totals.accounts_with_gaps)}</div></div>
        <p class="muted small">Accounts with at least one gap, across all checks. Gaps are reported exactly as found; none are merged or softened.</p>
        <a class="btn" href="#/run/${runId}/gaps">Open gap report</a></div>
    </div>
    <div class="card"><h2>Checks</h2>
      <table><thead><tr><th>Check</th><th>Question</th><th>Type</th><th class="num">Accounts</th><th>Result</th><th class="num">Gaps</th></tr></thead><tbody>
      ${checks.map((c) => `<tr class="click" data-check="${esc(c.check_id)}"><td><strong>${esc(c.check_id)}</strong></td>
        <td>${esc(c.question_text)}<div class="small muted">Sources: ${(c.sources || []).map(esc).join(", ") || "none"}${c.test_definition && c.test_definition.severity ? ` · ${esc(c.test_definition.severity)}` : ""}</div></td>
        <td><span class="tag">${esc(c.check_type)}</span>${c.check_type === "other" ? `<div class="small" style="color:var(--gap)">Not tested: reported as unanswered</div>` : ""}</td>
        <td class="num">${num(c.accounts)}</td><td>${stackBar(+c.evidenced, +c.gap, +c.cannot_determine)}<div class="small muted">${num(c.evidenced)} ok · ${num(c.cannot_determine)} unknown</div></td>
        <td class="num"><strong style="color:${+c.gap ? "var(--gap)" : "inherit"}">${num(c.gap)}</strong><div class="small muted">${num(c.accounts_with_gaps)} accts</div></td></tr>`).join("")}
      </tbody></table>
      <div class="small muted" style="margin-top:8px">Click a check to see its findings. <span class="badge b-evidenced">green</span> evidenced · <span class="badge b-gap">red</span> gap · <span class="badge b-cannot_determine">amber</span> cannot determine</div></div>`;
  el.querySelectorAll("tr[data-check]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${runId}/findings?check=${encodeURIComponent(tr.dataset.check)}`)));
}

/* ---------- findings / gap report ---------- */
async function findingsTab(el, d, runId, scale, q, gapsOnly) {
  const page = +(q.page || 0), size = 40;
  const f = { check: q.check || "", status: gapsOnly ? "gap" : q.status || "", account: q.account || "", severity: q.severity || "" };
  const params = new URLSearchParams({ limit: size, offset: page * size });
  if (f.check) params.set("check_id", f.check);
  if (f.status) params.set("status", f.status);
  if (f.account) params.set("account", f.account);
  if (f.severity) params.set("severity", f.severity);
  const data = await api(`/api/runs/${runId}/findings?${params}`);
  const base = `#/run/${runId}/${gapsOnly ? "gaps" : "findings"}`;
  const link = (over) => base + "?" + new URLSearchParams(Object.fromEntries(Object.entries({ ...q, ...over }).filter(([, v]) => v !== "" && v != null))).toString();
  el.innerHTML = `
    <div class="card"><form id="flt" class="row">
      <div><label>Check</label><select name="check"><option value="">All checks</option>${d.checks.map((c) => `<option value="${esc(c.check_id)}" ${c.check_id === f.check ? "selected" : ""}>${esc(c.check_id)} · ${esc(c.check_type)}</option>`).join("")}</select></div>
      ${gapsOnly ? "" : `<div><label>Status</label><select name="status"><option value="">Any</option>${["gap", "evidenced", "cannot_determine"].map((s) => `<option value="${s}" ${s === f.status ? "selected" : ""}>${s.replace("_", " ")}</option>`).join("")}</select></div>`}
      <div><label>Severity</label><select name="severity"><option value="">Any</option>${scale.map((s) => `<option ${s === f.severity ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
      <div style="flex:1;min-width:160px"><label>Account contains</label><input type="search" name="account" value="${esc(f.account)}" placeholder="ACC00110"></div>
      <div style="align-self:flex-end" class="row"><button class="primary">Filter</button>
        ${gapsOnly && d.run.status === "completed" ? `<a class="btn" href="/api/runs/${runId}/gap_report.csv">Download CSV</a>` : ""}</div>
    </form></div>
    <p class="muted small">${num(data.total)} ${gapsOnly ? "gap" : ""} findings${data.total ? ` · showing ${page * size + 1}–${Math.min((page + 1) * size, data.total)}` : ""}. ${gapsOnly ? "Ordered by the request's severity scale, most severe first." : "Gaps first."}</p>
    <div id="list">${data.rows.map(findingHtml(scale)).join("") || `<div class="empty">No findings match.</div>`}</div>
    <div class="pager">${page > 0 ? `<a class="btn" href="${link({ page: page - 1 })}">&larr; Previous</a>` : ""}
      ${(page + 1) * size < data.total ? `<a class="btn" href="${link({ page: page + 1 })}">Next &rarr;</a>` : ""}</div>`;
  el.querySelector("#flt").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = Object.fromEntries(new FormData(ev.target).entries());
    location.hash = base + "?" + new URLSearchParams(Object.entries(fd).filter(([, v]) => v)).toString();
  });
  el.querySelectorAll(".finding > .head").forEach((h) => h.addEventListener("click", () => {
    const body = h.nextElementSibling; body.hidden = !body.hidden;
  }));
  el.querySelectorAll("[data-rec]").forEach((b) => b.addEventListener("click", (ev) => { ev.stopPropagation(); showRecord(b.dataset.table, b.dataset.rec); }));
}

const findingHtml = (scale) => (f) => `
  <div class="finding"><div class="head">
    ${badge(f.status)} ${sevBadge(f.severity, scale)}
    <div class="reason"><div>${esc(f.reason)}</div>
      <div class="small muted"><span class="mono">${esc(f.account_id)}</span> · ${esc(f.check_id)} (${esc(f.check_type)})${f.subject_ref ? ` · ${esc(f.subject_ref)}` : ""}</div></div>
    <span class="tag">${f.citations.length} citation${f.citations.length === 1 ? "" : "s"}</span></div>
    <div class="body" hidden>
      ${f.citations.length ? f.citations.map(citeHtml).join("") : `<p class="muted small">No citation: this finding makes no claim either way.</p>`}
      <p class="small muted" style="margin-bottom:0">Finding #${f.finding_id}${f.evidence_query ? ` · query: <span class="mono">${esc(f.evidence_query)}</span>` : ""}</p>
    </div></div>`;

function citeHtml(c) {
  const ex = c.extract ? Object.entries(c.extract).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") : "";
  return `<div class="cite"><div class="meta"><span class="tag">${esc(c.role)}</span><strong>${esc(c.source_system)}</strong>
    <span class="mono">${esc(c.source_table)} / ${esc(c.record_key)}</span>
    <button class="link small" data-table="${esc(c.source_table)}" data-rec="${esc(c.record_key)}">View source record</button></div>
    <dl class="kv">${c.record_ts_utc ? `<dt>time (UTC)</dt><dd>${esc(c.record_ts_utc)}</dd>` : ""}${c.record_ts_original ? `<dt>as in source</dt><dd>${esc(c.record_ts_original)}</dd>` : ""}${ex}</dl></div>`;
}

async function showRecord(table, key) {
  const m = document.getElementById("modal");
  m.hidden = false;
  m.innerHTML = `<div class="box"><p class="muted">Loading…</p></div>`;
  m.onclick = (e) => { if (e.target === m) m.hidden = true; };
  try {
    const r = await api(`/api/record?table=${encodeURIComponent(table)}&key=${encodeURIComponent(key)}`);
    m.innerHTML = `<div class="box"><div class="row between"><h2 style="margin:0">Source record</h2><button id="close">Close</button></div>
      <p class="muted small mono">${esc(r.table)} · ${esc(r.key_column)} = ${esc(key)}</p>
      <dl class="kv">${Object.entries(r.record).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v)}</dd>`).join("")}</dl>
      <p class="small muted">Exactly as loaded into the raw layer (text, source time zone).</p></div>`;
  } catch (e) {
    m.innerHTML = `<div class="box"><div class="err">${esc(e.message)}</div><button id="close">Close</button></div>`;
  }
  document.getElementById("close").onclick = () => (m.hidden = true);
}

/* ---------- letter ---------- */
async function letterTab(el, runId, done) {
  if (!done) { el.innerHTML = `<div class="note">The response letter is drafted once the run has completed.</div>`; return; }
  const { markdown: md } = await api(`/api/runs/${runId}/letter`);
  let saved = null; try { saved = localStorage.getItem("letter:" + runId); } catch (_) {}
  const text = saved ?? md;
  el.innerHTML = `
    <div class="note">Draft for compliance review. Every figure comes from the recorded findings. Edits you make here stay in this browser; the stored findings never change.</div>
    <div class="row" style="margin-bottom:10px"><button id="dl" class="primary">Download .md</button><button id="cp">Copy</button><button id="rs">Reset to generated draft</button><span id="msg" class="small muted"></span></div>
    <div class="letter"><div><label>Edit</label><textarea id="ed" spellcheck="true"></textarea></div><div><label>Preview</label><div class="card md" id="pv"></div></div></div>`;
  const ed = document.getElementById("ed"), pv = document.getElementById("pv");
  ed.value = text; pv.innerHTML = markdown(text);
  ed.addEventListener("input", () => { pv.innerHTML = markdown(ed.value); try { localStorage.setItem("letter:" + runId, ed.value); } catch (_) {} });
  document.getElementById("dl").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([ed.value], { type: "text/markdown" })); a.download = `response_letter_${runId.slice(0, 8)}.md`; a.click();
  };
  document.getElementById("cp").onclick = async () => { await navigator.clipboard.writeText(ed.value); document.getElementById("msg").textContent = "Copied"; };
  document.getElementById("rs").onclick = () => { ed.value = md; pv.innerHTML = markdown(md); try { localStorage.removeItem("letter:" + runId); } catch (_) {} };
}

/* ---------- pack ---------- */
async function packTab(el, runId, done) {
  if (!done) { el.innerHTML = `<div class="note">The evidence pack is built once the run has completed.</div>`; return; }
  const { markdown: md } = await api(`/api/runs/${runId}/index`);
  el.innerHTML = `<div class="card"><div class="row between"><h2 style="margin:0">Evidence pack</h2>
      <div class="row"><a class="btn primary" href="/api/runs/${runId}/pack.zip">Download pack (.zip)</a><a class="btn" href="/api/runs/${runId}/gap_report.csv">Gap report (.csv)</a></div></div>
    <p class="muted small">The zip holds the index, one extract per check (a row per finding with its citations), the gap report and the draft response letter.</p>
    <div class="md">${markdown(md)}</div></div>`;
}

/* ---------- score ---------- */
async function scoreTab(el, runId, done) {
  if (!done) { el.innerHTML = `<div class="note">Score a run once it has completed.</div>`; return; }
  const keys = await api("/api/gap-keys");
  el.innerHTML = `<div class="card"><h2>Score against a gap key</h2>
    <p class="muted small">Compares the gaps this run reported with the true gaps at (account, question) level. Target: recall ≥ 95%, false gaps &lt; 5%, no claims without a citation.</p>
    <form id="sf" class="row">
      ${keys.length ? `<div><label>Gap key on this server</label><select name="key_name"><option value="">Choose…</option>${keys.map((k) => `<option>${esc(k)}</option>`).join("")}</select></div>` : ""}
      <div><label>…or upload a gap key (CSV)</label><input type="file" name="file" accept=".csv"></div>
      <div><label>Account column</label><input type="text" name="account_col" value="account_id" style="width:130px"></div>
      <div><label>Question column</label><input type="text" name="check_col" value="question_ref" style="width:130px"></div>
      <div style="align-self:flex-end"><button class="primary">Score</button></div></form><div id="sr"></div></div>`;
  document.getElementById("sf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = document.getElementById("sr");
    out.innerHTML = `<p class="muted">Scoring…</p>`;
    try {
      const s = await api(`/api/runs/${runId}/score`, { method: "POST", body: new FormData(ev.target) });
      const row = (label, val, ok, target) => `<tr><td>${label}</td><td class="num"><strong>${val}</strong></td><td><span class="badge ${ok ? "b-completed" : "b-failed"}">${ok ? "PASS" : "FAIL"}</span></td><td class="muted">${target}</td></tr>`;
      const list = (t, a) => (a.length ? `<h3>${t} (${a.length})</h3><p class="mono small">${a.slice(0, 40).map((x) => esc(x.join(" · "))).join("<br>")}${a.length > 40 ? "<br>…" : ""}</p>` : "");
      out.innerHTML = `<table style="margin-top:14px"><thead><tr><th>Measure</th><th class="num">Result</th><th></th><th>Target</th></tr></thead><tbody>
        ${row("Gap recall", (s.recall * 100).toFixed(1) + `% (${s.matched}/${s.true_gaps})`, s.recall >= 0.95, "≥ 95%")}
        ${row("False-gap rate", (s.false_gap_rate * 100).toFixed(1) + `% (${s.false_gaps.length}/${s.reported_gaps})`, s.false_gap_rate < 0.05, "< 5%")}
        ${row("Claims without a citation", s.unsupported_claims, s.unsupported_claims === 0, "0")}</tbody></table>${list("Missed gaps", s.missed)}${list("False gaps", s.false_gaps)}`;
    } catch (e) { out.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  });
}

/* ---------- SQL query ---------- */
const SAMPLES = [
  ["Rows loaded per source", `SELECT 'D4 contact log' AS source, count(*) AS rows FROM staging.d4_contacts
UNION ALL SELECT 'D5 consent', count(*) FROM staging.d5_consents
UNION ALL SELECT 'D10 recordings', count(*) FROM staging.d10_recordings
UNION ALL SELECT 'D11 verification', count(*) FROM staging.d11_verifications
UNION ALL SELECT 'Notices', count(*) FROM staging.notices
UNION ALL SELECT 'Collectors', count(*) FROM staging.collectors`],
  ["Messages sent before consent (compared in UTC)", `SELECT c.account_id, c.contact_id, c.channel, c.contact_ts_utc AS message_utc,
       min(s.consent_ts_utc) AS first_consent_utc
FROM staging.d4_contacts c
LEFT JOIN staging.d5_consents s ON s.account_id = c.account_id AND s.channel = c.channel
WHERE c.channel IN ('whatsapp', 'sms')
GROUP BY c.account_id, c.contact_id, c.channel, c.contact_ts_utc
HAVING min(s.consent_ts_utc) IS NULL OR min(s.consent_ts_utc) >= c.contact_ts_utc
ORDER BY c.contact_ts_utc
LIMIT 50`],
  ["Calls outside the D12 calling hours (IST)", `SELECT c.account_id, c.contact_id, c.contact_ts_src AS call_time_ist, c.collector_id
FROM staging.d4_contacts c, staging.d12_policy s, staging.d12_policy e
WHERE c.channel = 'call' AND s.policy_key = 'calling_hours_start' AND e.policy_key = 'calling_hours_end'
  AND NOT ((c.contact_ts_utc AT TIME ZONE 'Asia/Kolkata')::time >= s.policy_value::time
       AND (c.contact_ts_utc AT TIME ZONE 'Asia/Kolkata')::time <  e.policy_value::time)
ORDER BY c.contact_ts_utc
LIMIT 50`],
  ["Account-days over the daily call limit", `SELECT account_id, (contact_ts_utc AT TIME ZONE 'Asia/Kolkata')::date AS day, count(*) AS calls
FROM staging.d4_contacts, staging.d12_policy p
WHERE channel = 'call' AND p.policy_key = 'max_calls_per_day'
GROUP BY account_id, day, p.policy_value
HAVING count(*) > p.policy_value::int
ORDER BY calls DESC, day`],
  ["Connected calls with no recording", `SELECT c.account_id, c.contact_id, c.contact_ts_src AS call_time_ist
FROM staging.d4_contacts c
LEFT JOIN staging.d10_recordings r ON r.contact_id = c.contact_id
WHERE c.channel = 'call' AND c.outcome = 'connected' AND r.recording_id IS NULL
ORDER BY c.contact_ts_utc
LIMIT 50`],
  ["Calls by collectors with no valid certificate that day", `SELECT c.account_id, c.contact_id, c.collector_id,
       (c.contact_ts_utc AT TIME ZONE 'Asia/Kolkata')::date AS call_date
FROM staging.d4_contacts c
WHERE c.channel = 'call' AND NOT EXISTS (
  SELECT 1 FROM staging.certifications x WHERE x.collector_id = c.collector_id
    AND (c.contact_ts_utc AT TIME ZONE 'Asia/Kolkata')::date BETWEEN x.valid_from AND x.valid_to)
ORDER BY call_date
LIMIT 50`],
  ["Dues disclosed without prior verification", `SELECT c.account_id, c.contact_id, c.contact_ts_utc AS call_utc, v.verified_ts_utc, v.result
FROM staging.d4_contacts c
LEFT JOIN staging.d11_verifications v ON v.contact_id = c.contact_id
WHERE c.outcome = 'connected' AND c.dues_disclosed
  AND (v.verification_id IS NULL OR v.result <> 'passed' OR v.verified_ts_utc >= c.contact_ts_utc)
ORDER BY c.contact_ts_utc
LIMIT 50`],
];

async function sqlPage() {
  app.innerHTML = `<h1>SQL query</h1>
    <p class="muted">Run a read-only SELECT against the data. Timestamps in the <span class="mono">staging</span> views are already UTC (<span class="mono">*_utc</span>). This is the same warehouse SQL tool the agent uses: read-only role, one statement, 30 s limit.</p>
    <div class="card">
      <div class="row between"><div style="flex:1;min-width:240px"><label for="samp">Sample queries</label>
        <select id="samp">${SAMPLES.map(([n], i) => `<option value="${i}">${esc(n)}</option>`).join("")}</select></div>
        <div class="row" style="align-self:flex-end"><button class="primary" id="go">Run query</button><span class="small muted">Ctrl+Enter</span></div></div>
      <label for="q" style="margin-top:12px">Query</label><textarea id="q" spellcheck="false" style="min-height:190px"></textarea>
      <p class="small muted" style="margin-bottom:0">Views: staging.d4_contacts · d5_consents · d10_recordings · d11_verifications · d12_policy · notices · holidays · collectors · certifications</p>
    </div><div id="res"></div>`;
  const q = document.getElementById("q"), samp = document.getElementById("samp");
  const load = () => { q.value = SAMPLES[+samp.value][1]; };
  const run = async () => {
    const res = document.getElementById("res");
    res.innerHTML = `<div class="card muted">Running…</div>`;
    const t0 = performance.now();
    try {
      const r = await api("/api/sql", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: q.value }) });
      const ms = Math.round(performance.now() - t0);
      res.innerHTML = `<div class="card"><div class="row between"><div class="muted small">${num(r.rows.length)} row${r.rows.length === 1 ? "" : "s"}${r.truncated ? " (truncated)" : ""} · ${ms} ms</div>
        ${r.rows.length ? `<button id="csv">Download CSV</button>` : ""}</div>
        ${r.rows.length ? `<div style="overflow:auto;max-height:520px;margin-top:8px"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>
          ${r.rows.map((row) => `<tr>${row.map((v) => `<td class="${typeof v === "number" ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">The query returned no rows.</div>`}</div>`;
      const b = document.getElementById("csv");
      if (b) b.onclick = () => {
        const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
        const csv = [r.columns, ...r.rows].map((row) => row.map(cell).join(",")).join("\n");
        const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" })); a.download = "query_result.csv"; a.click();
      };
    } catch (e) { res.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  samp.addEventListener("change", () => { load(); run(); });
  document.getElementById("go").onclick = run;
  q.addEventListener("keydown", (e) => { if (e.ctrlKey && e.key === "Enter") run(); });
  load(); run();
}

/* ---------- boot ---------- */
(async () => {
  try {
    state.config = await api("/api/config");
    document.getElementById("parser-badge").textContent = state.config.parser === "llm" ? `Parser: ${state.config.model}` : "Parser: keyword fallback (no API key)";
  } catch (_) {}
  route();
})();
