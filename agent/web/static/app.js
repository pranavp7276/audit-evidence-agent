"use strict";
const app = document.getElementById("app");
const state = { poll: null, config: {}, rules: null, seq: 0 };

/* ================= helpers ================= */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (n) => Number(n || 0).toLocaleString();
const when = (s) => (s ? new Date(s).toLocaleString() : "");
const fdate = (s) => (s ? new Date(String(s).slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "");
const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
const duration = (a, b) => {
  if (!a || !b) return "";
  const s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000));
  return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
};
const STATUS_LABEL = { evidenced: "Evidenced", gap: "Gap", cannot_determine: "Cannot determine" };
const DISP_LABEL = { open: "Open", confirmed: "Confirmed", disputed: "Disputed", remediation_planned: "Remediation planned", evidence_obtained: "Evidence obtained" };
const DISP_FOR = { gap: ["open", "confirmed", "disputed", "remediation_planned"], cannot_determine: ["open", "evidence_obtained"] };
const SOURCE_TABLE = { call: "cn_core.tele_process_instance_call_logs", whatsapp: "cn_core.communication_dashboard_t", sms: "cn_core.communication_dashboard_t",
  consent: "compliance.customer_consent", recording: "compliance.call_recording", notice: "compliance.notice" };

async function api(path, opts) {
  const gen = state.seq, isGet = !opts || !opts.method || opts.method === "GET";
  const r = await fetch(path, opts);
  if (isGet && gen !== state.seq) throw Object.assign(new Error("superseded"), { stale: true }); // the user already navigated elsewhere
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw new Error(msg);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

const reviewer = () => { try { return localStorage.getItem("reviewer") || ""; } catch (_) { return ""; } };
function setReviewer(v) { try { localStorage.setItem("reviewer", v); } catch (_) {} renderWho(); }
function renderWho() { document.getElementById("who").textContent = reviewer() ? `Signed in as ${reviewer()}` : "Set your name"; }
function needName() {
  if (reviewer()) return reviewer();
  const n = (window.prompt("Your name (recorded on every review and letter change):") || "").trim();
  if (n) setReviewer(n);
  return n;
}

const badge = (status) => `<span class="badge b-${esc(status)}">${esc(STATUS_LABEL[status] || String(status).replace(/_/g, " "))}</span>`;
const dispBadge = (d) => `<span class="badge b-${esc(d)}">${esc(DISP_LABEL[d] || d)}</span>`;
function sevBadge(label, scale) {
  if (!label) return "";
  const i = Math.min(Math.max(scale.indexOf(label), 0), 3);
  return `<span class="badge sev sev-${i}">${esc(label)}</span>`;
}
function stackBar(e, g, u) {
  const t = (e + g + u) || 1;
  return `<div class="bar" title="${e} evidenced, ${g} gap, ${u} cannot determine"><span class="e" style="width:${(e / t) * 100}%"></span><span class="g" style="width:${(g / t) * 100}%"></span><span class="u" style="width:${(u / t) * 100}%"></span></div>`;
}
const stat = (n, label, cls = "") => `<div class="stat ${cls}"><div class="n">${num(n)}</div><div class="l">${esc(label)}</div></div>`;
const help = (topic) => `<a class="help no-print" href="#/guide/${topic}">Help</a>`;
const info = (type) => (state.rules && state.rules.checks[type]) || { title: type, tests: "", sources: [] };

function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_([^_]+)_(?=[\s).,;]|$)/g, "$1<em>$2</em>").replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
}
function markdown(md) {
  const out = []; let list = false, table = [];
  const flush = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|\s*-/.test(r)).map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    out.push("<table><thead><tr>" + rows[0].map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>" +
      rows.slice(1).map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table>");
    table = [];
  };
  for (const line of md.split("\n")) {
    if (line.startsWith("|")) { table.push(line); continue; }
    flush();
    if (/^- /.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(line.slice(2))}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    const h = line.match(/^(#{1,3}) (.*)/);
    if (h) out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  flush(); if (list) out.push("</ul>");
  return out.join("\n");
}
function download(name, text, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
}

/* ================= routing ================= */
function stopPolling() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
function parseHash() {
  const [path, query = ""] = location.hash.slice(1).split("?");
  return { parts: path.split("/").filter(Boolean), q: Object.fromEntries(new URLSearchParams(query)) };
}
async function route() {
  state.seq++;
  stopPolling();
  const { parts, q } = parseHash();
  const section = { new: "new", rules: "rules", kb: "kb", guardrails: "guardrails", guide: "guide" }[parts[0]] || "runs";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === section));
  try {
    if (parts[0] === "new") await newRequestPage();
    else if (parts[0] === "rules") await rulesPage(app, true);
    else if (parts[0] === "guide") guidePage(parts[1] || "start");
    else if (parts[0] === "kb" && parts[1]) await kbDocPage(parts[1]);
    else if (parts[0] === "kb") await kbPage();
    else if (parts[0] === "guardrails") await guardrailsPage(q);
    else if (parts[0] === "sql") await sqlPage();
    else if (parts[0] === "run" && parts[1]) await workspace(parts[1], parts[2] || "summary", parts[3], q);
    else await homePage();
  } catch (e) {
    if (e.stale) return;
    app.innerHTML = `<div class="err">${esc(e.message)}</div><p><a href="#/">Back to audit requests</a></p>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);

/* ================= home ================= */
async function homePage() {
  const runs = await api("/api/runs");
  const today = new Date().toISOString().slice(0, 10);
  let seen = false; try { seen = !!localStorage.getItem("seenGuide"); } catch (_) {}
  app.innerHTML = `
    ${seen ? "" : `<div class="note info hint"><span><strong>New here?</strong> The <a href="#/guide/start">Guide</a> explains how to run an audit, review the results and work with the data. It takes five minutes.</span><button id="hide-hint">Got it</button></div>`}
    <div class="row between"><div><h1>Audit requests ${help("audit")}</h1>
      <p class="muted">Each audit request from a lender or regulator becomes an engagement: the platform tests the evidence for every sampled account, and you review the gaps, follow up what could not be proven, and release the response.</p></div>
      <a class="btn primary big" href="#/new">New audit request</a></div>
    <div class="card">
      ${runs.length ? `<table><thead><tr><th>Request</th><th>Status</th><th>Response due</th><th class="num">Accounts</th><th>Results</th><th class="num">Gaps reviewed</th><th>Letter</th></tr></thead><tbody>
        ${runs.map((r) => {
          const overdue = r.response_due && String(r.response_due).slice(0, 10) < today && r.letter_status !== "approved";
          return `<tr class="click" data-run="${r.run_id}"><td><strong>${esc(r.request_id)}</strong><div class="small muted">${esc(r.lender || "")}</div><div class="small muted">${when(r.started_at)}</div></td>
          <td>${badge(r.status)}</td><td class="small">${r.response_due ? fdate(r.response_due) : "—"}${overdue ? ` <span class="badge b-failed">overdue</span>` : ""}</td>
          <td class="num">${num(r.accounts)}</td><td style="min-width:150px">${stackBar(+r.evidenced, +r.gaps, +r.cannot_determine)}<div class="small muted">${num(r.gaps)} gaps · ${num(r.cannot_determine)} to follow up</div></td>
          <td class="num">${num(r.gaps_reviewed)} / ${num(r.gaps)}</td><td>${r.letter_status ? `<span class="badge b-${r.letter_status}">${esc(r.letter_status.replace("_", " "))}</span>` : `<span class="muted small">not started</span>`}</td></tr>`;
        }).join("")}</tbody></table>` : `<div class="empty"><p>No audit requests yet.</p><a class="btn primary" href="#/new">Start your first audit request</a></div>`}
    </div>`;
  app.querySelectorAll("tr[data-run]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${tr.dataset.run}`)));
  const hh = document.getElementById("hide-hint");
  if (hh) hh.onclick = () => { try { localStorage.setItem("seenGuide", "1"); } catch (_) {} hh.closest(".note").remove(); };
}

/* ================= new request: upload, confirm interpretation, run ================= */
const draft = { form: {}, preview: null };

async function newRequestPage() {
  const examples = await api("/api/examples");
  const f = draft.form;
  app.innerHTML = `
    <h1>New audit request ${help("audit")}</h1>
    <div class="steps"><span class="${draft.preview ? "done" : "on"}">1. Upload the request</span><span class="${draft.preview ? "on" : ""}">2. Confirm how it is read</span><span>3. Run and review</span></div>
    <div class="card"><form id="intake">
      <div class="grid cols2">
        <div><label for="rid">Request reference</label><input id="rid" type="text" value="${esc(f.rid || "CO-04")}" required></div>
        <div><label for="lender">Requested by (lender or regulator)</label><input id="lender" type="text" value="${esc(f.lender || "")}" placeholder="e.g. Example Lender Ltd"></div>
        <div><label for="due">Response due</label><input id="due" type="date" value="${esc(f.due || "")}"></div>
        <div><label for="file">Request document (PDF, .eml or text)</label><input id="file" type="file" accept=".pdf,.eml,.txt,.md"></div>
      </div>
      <div style="margin-top:12px"><div class="row between"><label for="text">…or paste the request text</label>
        <span class="small muted">Try an example: <button type="button" class="link" data-instruction>plain instruction</button>${examples.map((n) => ` · <button type="button" class="link" data-example="${esc(n)}">${esc(n)}</button>`).join("")}</span></div>
        <textarea id="text" placeholder="Paste the numbered questions, the severity scale and the sampled accounts, or simply write the instruction, e.g. &quot;Run a compliance audit for all accounts contacted in the previous month, sample size 300&quot;.">${esc(f.text || "")}</textarea></div>
      <details><summary>Have a specific list of accounts to test?</summary><div class="grid cols2">
        <div><label for="accts">Loan account numbers (comma separated)</label><input id="accts" type="text" value="${esc(f.accts || "")}" placeholder="CNF123456789, CNF987654321"></div></div></details>
      <div class="row" style="margin-top:14px"><button class="primary big" id="read">Read the request</button><span id="intake-err"></span></div>
    </form></div>
    <div id="confirm"></div>`;
  app.querySelector("[data-instruction]").addEventListener("click", () => {
    document.getElementById("text").value = "Run a compliance audit for all the accounts reached out within the previous month. Check whether all the guardrails in Rules & data are being followed. Use a sample size of 300.";
    document.getElementById("rid").value = "AUDIT-PREV-MONTH";
  });
  app.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", async () => {
    const ex = await api("/api/examples/" + encodeURIComponent(b.dataset.example));
    document.getElementById("text").value = ex.text;
    document.getElementById("rid").value = ex.name.replace(/\.[^.]+$/, "");
  }));
  document.getElementById("intake").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = document.getElementById("read"); btn.disabled = true; btn.textContent = "Reading…";
    const fd = new FormData();
    fd.append("request_id", document.getElementById("rid").value);
    fd.append("text", document.getElementById("text").value);
    const file = document.getElementById("file").files[0];
    if (file) fd.append("file", file);
    draft.form = { rid: document.getElementById("rid").value, lender: document.getElementById("lender").value, due: document.getElementById("due").value,
      text: document.getElementById("text").value, accts: document.getElementById("accts").value };
    try {
      draft.sample = null;
      draft.preview = await api("/api/requests/preview", { method: "POST", body: fd });
      draft.form.text = draft.preview.text; // the extracted text (also for PDFs)
      renderConfirm();
    } catch (e) {
      document.getElementById("intake-err").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`;
    }
    btn.disabled = false; btn.textContent = "Read the request";
  });
  if (draft.preview) renderConfirm();
}

function checkOptions(sel) {
  return Object.entries(state.config.check_types || {}).map(([k, t]) => `<option value="${k}" ${k === sel ? "selected" : ""}>${esc(t)}</option>`).join("");
}
function renderConfirm() {
  const p = draft.preview, el = document.getElementById("confirm");
  const questions = new Set(p.checks.map((c) => c.question_ref)).size;
  const listed = p.accounts || (draft.form.accts || "").split(",").filter((x) => x.trim()).length;
  const S = (draft.sample ||= { start: p.period ? p.period.start : "", end: p.period ? p.period.end : "", label: p.period ? p.period.label : "", size: p.size || "", eligible: p.eligible });
  const canRun = () => !!(listed || S.size);
  el.innerHTML = `
    <div class="card"><h2>Confirm how the request is read</h2>
      ${p.checks.length ? "" : `<div class="err">No checks could be made from this text. Describe what to test (for example “check consent, calling hours and verification for accounts contacted last month”) or paste numbered questions.</div>`}
      ${p.instruction ? `<div class="note">Your request is an instruction rather than numbered questions, so the platform chose ${p.checks.length} guardrail check(s) to test${p.checks.length === 7 ? " (a full compliance audit: every guardrail listed in Rules &amp; data)" : ""}. Severities use the default scale ${p.scale.map(esc).join(" › ")} because the request gave none. Change anything below before running.</div>` : ""}
      <p class="muted">${p.instruction ? `Guardrails to test: ${p.checks.length}.` : `${questions} question(s) became ${p.checks.length} check(s)${p.parser === "keyword" ? " using the keyword reader (no AI key is configured), so please check each row" : " by the AI reader; please check each row"}.`}
        Questions can be vague or bundle several tests: change the test, set the severity from the request's scale, or split a bundled question. A question that fits no test is reported as <em>unanswered</em>, never dropped.</p>
      <table class="wiz"><thead><tr><th>Check</th><th>Question as written</th><th>Test applied</th><th>Severity</th><th></th></tr></thead><tbody>
      ${p.checks.map((c, i) => `<tr data-i="${i}"><td><input type="text" data-f="check_id" value="${esc(c.check_id)}" style="width:70px"><div class="small muted">${esc(c.question_ref)}</div></td>
        <td>${esc(c.question_text)}</td>
        <td><select data-f="check_type">${checkOptions(c.check_type)}</select><div class="exp" data-exp>${esc(info(c.check_type).tests)}</div></td>
        <td><select data-f="severity"><option value="">(none given)</option>${p.scale.map((s) => `<option ${s === c.severity ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></td>
        <td><button type="button" class="link" data-split="${i}" title="Add another check for the same question">Split</button>${p.checks.filter((x) => x.question_ref === c.question_ref).length > 1 ? ` · <button type="button" class="link" data-del="${i}">Remove</button>` : ""}</td></tr>`).join("")}
      </tbody></table>
      <div class="small muted" style="margin-top:8px">Severity scale found in the request: ${p.scale.length ? p.scale.map(esc).join(" › ") : "none"}. Gaps with no severity are graded at the most severe level.</div>
    </div>
    <div class="card"><h2>Period and sample</h2>
      ${listed ? `<p><strong>${num(listed)}</strong> accounts are ${p.accounts ? "listed in the request" : "supplied"} and will all be tested.</p>`
        : `<p class="muted">The request lists no accounts, so the platform draws a random sample of the accounts that had a contact in the period. The same request always draws the same sample.</p>`}
      <div class="grid cols4" style="grid-template-columns:repeat(4,minmax(0,1fr))">
        <div><label for="ps">Period starts</label><input id="ps" type="date" value="${esc(S.start)}"></div>
        <div><label for="pe">Period ends (not included)</label><input id="pe" type="date" value="${esc(S.end)}"></div>
        ${listed ? "" : `<div><label for="sz">Sample size</label><input id="sz" type="number" min="1" max="${p.max_sample}" value="${esc(S.size)}" placeholder="300"></div>`}
        <div style="align-self:flex-end"><button type="button" id="recount">Recount accounts</button></div></div>
      <p id="elig" class="small muted" style="margin-bottom:0"></p>
      ${S.label ? `<p class="small muted" style="margin:6px 0 0">Read from the request: ${esc(S.label)}. Calls and messages outside the period are not tested; notices are tested over their own history. Days are India calendar days.</p>` : `<p class="small muted" style="margin:6px 0 0">No period given: every contact on record is tested.</p>`}
      ${p.accounts ? `<p class="muted small" style="margin-bottom:6px"><strong>${num(p.matched)}</strong> of ${num(p.accounts)} references matched a loan account${p.unmatched.length ? `; <strong>${p.unmatched.length} matched nothing</strong>` : ""}${p.ambiguous.length ? `; <strong>${p.ambiguous.length} are ambiguous</strong>` : ""}. They stay visible on the audit and are not tested until resolved.</p>` : ""}
      ${p.unmatched.length ? `<div class="note"><strong>Unmatched:</strong> ${p.unmatched.slice(0, 10).map(esc).join(", ")}${p.unmatched.length > 10 ? ", …" : ""}. Check these references with the auditor.</div>` : ""}
      ${p.ambiguous.length ? `<div class="note"><strong>Ambiguous:</strong> ${p.ambiguous.slice(0, 4).map((x) => `${esc(x.ref)} (${esc(x.note)})`).join(" · ")}</div>` : ""}
    </div>
    <div class="row"><button class="primary big" id="run" ${canRun() && p.checks.length ? "" : "disabled"}>Run audit</button><span class="muted small">A 300-account, 10-question request normally completes in a couple of minutes.</span><span id="run-err"></span></div>`;
  const sync = () => el.querySelectorAll("tr[data-i]").forEach((tr) => {
    const c = p.checks[+tr.dataset.i];
    tr.querySelectorAll("[data-f]").forEach((inp) => (c[inp.dataset.f] = inp.value || null));
  });
  el.querySelectorAll("tr[data-i] [data-f]").forEach((inp) => inp.addEventListener("change", () => {
    sync();
    if (inp.dataset.f === "check_type") inp.closest("tr").querySelector("[data-exp]").textContent = info(inp.value).tests;
  }));
  el.querySelectorAll("[data-split]").forEach((b) => b.addEventListener("click", () => {
    sync();
    const i = +b.dataset.split, c = p.checks[i], same = p.checks.filter((x) => x.question_ref === c.question_ref);
    if (c.check_id === c.question_ref) c.check_id = c.question_ref + "a";
    const next = c.question_ref + String.fromCharCode(97 + same.length);
    p.checks.splice(i + 1, 0, { ...c, check_id: next, check_type: "other" });
    renderConfirm();
  }));
  el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
    sync();
    const ref = p.checks[+b.dataset.del].question_ref;
    p.checks.splice(+b.dataset.del, 1);
    const left = p.checks.filter((x) => x.question_ref === ref);
    if (left.length === 1 && left[0].check_id === ref + "a") left[0].check_id = ref; // no longer split
    renderConfirm();
  }));
  const elig = document.getElementById("elig"), runBtn = document.getElementById("run");
  const readSample = () => {
    S.start = document.getElementById("ps").value; S.end = document.getElementById("pe").value;
    const sz = document.getElementById("sz"); if (sz) S.size = sz.value;
  };
  const paintElig = () => {
    if (listed) { elig.textContent = S.start ? `Tests apply to contacts from ${S.start} up to (not including) ${S.end}.` : ""; return; }
    const n = S.eligible, want = +S.size;
    elig.innerHTML = n == null ? "" : `<strong>${num(n)}</strong> account(s) had at least one contact ${S.start ? "in this period" : "on record"}${want ? `; ${want > n ? `only ${num(n)} can be sampled (you asked for ${num(want)})` : `${num(want)} will be drawn at random`}` : ""}.`;
    runBtn.disabled = !(p.checks.length && (listed || want) && (n == null || n > 0));
  };
  const recount = async () => {
    readSample();
    try { S.eligible = (await api(`/api/population?start=${S.start}&end=${S.end}`)).eligible; } catch (e) { elig.innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; return; }
    paintElig();
  };
  document.getElementById("recount").addEventListener("click", recount);
  ["ps", "pe", "sz"].forEach((id) => { const i = document.getElementById(id); if (i) i.addEventListener("input", () => { readSample(); paintElig(); }); });
  paintElig();
  document.getElementById("run").addEventListener("click", async () => {
    sync(); readSample();
    const ids = p.checks.map((c) => c.check_id.trim());
    if (new Set(ids).size !== ids.length || ids.some((x) => !x)) { document.getElementById("run-err").innerHTML = `<span class="badge b-failed">Each check needs its own id</span>`; return; }
    const who = needName(); if (!who) return;
    const fd = new FormData(), f = draft.form;
    fd.append("request_id", f.rid); fd.append("lender", f.lender || ""); fd.append("response_due", f.due || ""); fd.append("created_by", who);
    fd.append("text", p.text); fd.append("source", p.source); fd.append("accounts", f.accts || "");
    if (S.start && S.end) { fd.append("period_start", S.start); fd.append("period_end", S.end); fd.append("period_label", S.label && S.start === (p.period || {}).start && S.end === (p.period || {}).end ? S.label : ""); }
    if (!listed && S.size) fd.append("sample_size", S.size);
    fd.append("checks", JSON.stringify(p.checks.map((c) => ({ ...c, check_id: c.check_id.trim() })))); fd.append("scale", JSON.stringify(p.scale));
    const btn = document.getElementById("run"); btn.disabled = true; btn.textContent = "Starting…";
    try {
      const r = await api("/api/runs", { method: "POST", body: fd });
      draft.preview = null; draft.form = {};
      location.hash = `#/run/${r.run_id}`;
    } catch (e) { document.getElementById("run-err").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; btn.disabled = false; btn.textContent = "Run audit"; }
  });
  el.scrollIntoView({ behavior: "smooth" });
}

/* ================= engagement workspace ================= */
const TABS = [["summary", "Summary"], ["questions", "Questions"], ["gaps", "Gap register"], ["followup", "Follow-up"], ["accounts", "Accounts"], ["letter", "Response letter"], ["pack", "Evidence pack"], ["rules", "Rules & data"]];

async function workspace(runId, tab, sub, q) {
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
  else if (tab === "rules") await rulesPage(el, false, runId, done);
  if (run.status === "running") {
    state.poll = setInterval(async () => {
      const n = await api(`/api/runs/${runId}`).catch(() => null);
      if (n && (n.run.status !== "running" || n.tested_checks !== d.tested_checks)) route();
    }, 2500);
  }
}

/* ---------- summary ---------- */
function summary(el, d, runId, scale) {
  const { checks, totals, severity, coverage, collectors, months, review, letter } = d;
  const gaps = +totals.gap, sampled = coverage.sampled;
  const crit = severity[0];
  const rv = (status, disp) => review.filter((r) => r.status === status && (disp === undefined || r.disposition === disp)).reduce((a, r) => a + +r.n, 0);
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
    <div class="grid cols2" style="margin-top:14px">
      <div class="card"><h2>Your next steps</h2><ul class="todo">
        ${step(!coverage.unresolved.length && !coverage.no_data.length, false, "Check the sample", coverage.unresolved.length ? `${coverage.unresolved.length} account references are unmatched or ambiguous` : coverage.no_data.length ? `${coverage.no_data.length} sampled accounts have no activity` : `All ${num(sampled)} sampled accounts matched and have activity`, "")}
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
  el.querySelectorAll("tr[data-q]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${runId}/questions/${encodeURIComponent(tr.dataset.q)}`)));
}

/* ---------- questions ---------- */
async function questionsTab(el, d, runId, scale) {
  const resp = await api(`/api/runs/${runId}/responses`);
  const groups = {};
  d.checks.forEach((c) => (groups[c.question_ref] ||= []).push(c));
  el.innerHTML = `<p class="muted">Each question as the platform read it, how it was tested, and the result. Add the management comment that will appear in the response letter.</p>` +
    Object.entries(groups).map(([ref, cs]) => {
      const r = resp[ref];
      return `<div class="qcard"><div class="qh"><div class="row between"><div><strong>${esc(ref)}</strong> &nbsp;${esc(cs[0].question_text)}</div><a class="btn" href="#/run/${runId}/questions/${encodeURIComponent(ref)}">Open findings</a></div></div>
        <div class="qb"><div>${cs.map((c) => {
          const i = info(c.check_type);
          return `<div class="interp"><b>${esc(c.check_id)} · ${esc(i.title)}</b>${c.test_definition && c.test_definition.severity ? ` &nbsp;${sevBadge(c.test_definition.severity, scale)}` : ""}${c.test_definition && c.test_definition.guardrail ? ` <span class="tag" title="The guardrail version this audit applied">guardrail ${esc(c.test_definition.guardrail.id)} v${esc(c.test_definition.guardrail.version)}${c.test_definition.priority_weight > 1 ? ` · priority ${esc(c.test_definition.priority_weight)}` : ""}</span>` : ""}<br>${esc(i.tests)}
            <div class="small muted" style="margin-top:4px">Gap when: ${esc(i.gap)}<br>Sources: ${(i.sources || []).map(esc).join(", ") || "none"}</div></div>
            <div style="margin:8px 0 14px">${c.check_type === "other" ? `<div class="note">Not testable by the platform: this question will be reported as unanswered and needs a manual response.</div>` : `${stackBar(+c.accounts_ok, +c.accounts_gap, +c.accounts_unknown)}<div class="small muted">${num(c.accounts_ok)} compliant · <strong style="color:var(--gap)">${num(c.accounts_gap)} with gaps</strong> · ${num(c.accounts_unknown)} cannot determine (of ${num(c.accounts)} sampled)</div>`}</div>`;
        }).join("")}</div>
        <div><label for="mc-${esc(ref)}">Management comment (goes into the letter)</label>
          <textarea id="mc-${esc(ref)}" data-ref="${esc(ref)}" style="min-height:130px;font-family:inherit" placeholder="Explain root cause, remediation and timelines for the gaps in this question.">${esc(r ? r.body : "")}</textarea>
          <div class="row" style="margin-top:8px"><button class="primary" data-save="${esc(ref)}">Save comment</button><span class="small muted" data-msg="${esc(ref)}">${r ? `Last saved by ${esc(r.author)} on ${when(r.created_at)}` : "Not yet written"}</span></div></div></div></div>`;
    }).join("");
  el.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", async () => {
    const ref = b.dataset.save, who = needName(); if (!who) return;
    const msg = el.querySelector(`[data-msg="${ref}"]`);
    try {
      await api(`/api/runs/${runId}/responses/${encodeURIComponent(ref)}`, { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: el.querySelector(`textarea[data-ref="${ref}"]`).value, author: who }) });
      msg.textContent = `Saved by ${who} just now`;
    } catch (e) { msg.innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  }));
}

/* ---------- findings (shared by questions, gap register, follow-up, account file) ---------- */
function findingItem(f, scale, reviewable, selectable) {
  const opts = DISP_FOR[f.status];
  return `<div class="finding" data-id="${f.finding_id}"><div class="head">
    ${selectable ? `<input type="checkbox" class="sel" data-id="${f.finding_id}" title="Select for a bulk decision" style="width:auto;margin-top:5px">` : ""}
    ${badge(f.status)} ${sevBadge(f.severity, scale)} ${f.status !== "evidenced" ? dispBadge(f.disposition) : ""}
    <div class="reason"><div>${esc(f.reason)}</div><div class="small muted"><a class="mono" href="#/run/${f.run_id}/account/${encodeURIComponent(f.account_id)}" title="CN account id ${esc(f.account_id)}">${esc(f.account_number || f.account_id)}</a> · ${esc(f.check_id)} ${esc(info(f.check_type).title)}${f.subject_ref ? ` · ${esc(f.subject_ref)}` : ""}</div></div>
    ${f.priority_weight > 1 ? `<span class="tag" title="Review priority weight">priority ${f.priority_weight}</span>` : ""}<span class="tag">${f.citations.length} record${f.citations.length === 1 ? "" : "s"}</span></div>
    <div class="body" hidden>
      <div class="small"><strong>Test applied:</strong> ${esc(info(f.check_type).tests)}</div>
      ${f.citations.length ? f.citations.map(citeHtml).join("") : `<p class="muted small">No citation: this finding makes no claim either way.</p>`}
      ${reviewable && opts ? `<div class="review no-print"><div class="small muted" style="margin-bottom:6px">${f.reviewer ? `Last decision: ${dispBadge(f.disposition)} by ${esc(f.reviewer)}${f.review_comment ? ` — “${esc(f.review_comment)}”` : ""}` : "Not reviewed yet."} A disputed gap is still reported.</div>
        <div class="row"><select data-disp style="width:auto">${opts.map((o) => `<option value="${o}" ${o === f.disposition ? "selected" : ""}>${DISP_LABEL[o]}</option>`).join("")}</select>
        <input type="text" data-comment placeholder="Comment (required to dispute or plan remediation)" style="flex:1;min-width:220px"><button data-savereview class="primary">Save decision</button></div></div>` : ""}
      <p class="small muted" style="margin-bottom:0">Finding #${f.finding_id}${f.evidence_query ? ` · query: <span class="mono">${esc(f.evidence_query)}</span>` : ""}</p></div></div>`;
}

function citeHtml(c) {
  const ex = c.extract ? Object.entries(c.extract).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("") : "";
  return `<div class="cite"><div class="meta"><span class="tag">${esc(c.role)}</span><strong>${esc(c.source_system)}</strong><span class="mono">${esc(c.source_table)} / ${esc(c.record_key)}</span>
    <button class="link small" data-table="${esc(c.source_table)}" data-rec="${esc(c.record_key)}">View source record</button></div>
    <dl class="kv">${c.record_ts_utc ? `<dt>time (UTC)</dt><dd>${esc(c.record_ts_utc)}</dd>` : ""}${c.record_ts_original ? `<dt>as in source</dt><dd>${esc(c.record_ts_original)}</dd>` : ""}${ex}</dl></div>`;
}

function wireFindings(root, runId, onSaved) {
  root.addEventListener("click", async (ev) => {
    const head = ev.target.closest(".finding > .head");
    const rec = ev.target.closest("[data-rec]");
    const save = ev.target.closest("[data-savereview]");
    if (rec) { ev.stopPropagation(); showRecord(rec.dataset.table, rec.dataset.rec); return; }
    if (save) {
      const item = save.closest(".finding"), who = needName(); if (!who) return;
      try {
        await post(`/api/runs/${runId}/reviews`, { finding_ids: [+item.dataset.id], disposition: item.querySelector("[data-disp]").value,
          comment: item.querySelector("[data-comment]").value, reviewer: who });
        onSaved();
      } catch (e) { alert(e.message); }
      return;
    }
    if (head && !ev.target.closest("input,select,a,button")) head.nextElementSibling.hidden = !head.nextElementSibling.hidden;
  });
}

async function findingsPage(el, d, runId, scale, o) {
  const q = o.q || {}, page = +(q.page || 0), size = 30, fixed = o.fixed || {};
  const f = { question: fixed.question || q.question || "", severity: q.severity || "", disposition: q.disposition || "", account: q.account || "", status: fixed.status || q.status || "" };
  const params = new URLSearchParams({ limit: size, offset: page * size });
  if (f.question) params.set("question", f.question);
  ["status", "severity", "disposition", "account"].forEach((k) => f[k] && params.set(k, f[k]));
  const data = await api(`/api/runs/${runId}/findings?${params}`);
  data.rows.forEach((r) => (r.run_id = runId));
  const reviewable = d.run.status === "completed", selectable = reviewable && o.mode !== "question";
  const questions = [...new Set(d.checks.map((c) => c.question_ref))];
  const link = (over) => o.base + "?" + new URLSearchParams(Object.entries({ ...q, ...over }).filter(([, v]) => v !== "" && v != null)).toString();
  const title = o.mode === "gaps" ? "Gap register" : o.mode === "followup" ? "Follow-up: what could not be determined" : o.title;
  const blurb = o.mode === "gaps" ? "Every gap, most severe first. Open one to see the records it cites, then confirm it, dispute it with a reason, or record the remediation. A disputed gap is still reported."
    : o.mode === "followup" ? "Items where the evidence was missing or ambiguous, so no claim is made. Obtain the evidence, then record it here; until then they stay open in the response."
    : "All findings for this question, with the records they cite.";
  el.innerHTML = `
    ${o.mode === "question" ? `<p class="small"><a href="#/run/${runId}/questions">&larr; All questions</a></p>` : ""}
    <h2>${esc(title)} ${help("review")}</h2><p class="muted small">${blurb}</p>
    <div class="card no-print"><form id="flt" class="row">
      ${o.mode !== "question" ? `<div><label>Question</label><select name="question"><option value="">All</option>${questions.map((x) => `<option ${x === f.question ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>` : `<div><label>Status</label><select name="status"><option value="">Any</option>${["gap", "evidenced", "cannot_determine"].map((s) => `<option value="${s}" ${s === f.status ? "selected" : ""}>${STATUS_LABEL[s]}</option>`).join("")}</select></div>`}
      ${o.mode !== "followup" ? `<div><label>Severity</label><select name="severity"><option value="">Any</option>${scale.map((s) => `<option ${s === f.severity ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>` : ""}
      <div><label>Review status</label><select name="disposition"><option value="">Any</option>${Object.entries(DISP_LABEL).map(([k, v]) => `<option value="${k}" ${k === f.disposition ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div style="flex:1;min-width:150px"><label>Loan account contains</label><input type="search" name="account" value="${esc(f.account)}" placeholder="CNF123456789"></div>
      <div style="align-self:flex-end" class="row"><button class="primary">Filter</button>
        ${o.mode === "gaps" && reviewable ? `<a class="btn" href="/api/runs/${runId}/files/gap_report.csv">Download CSV</a>` : o.mode === "followup" && reviewable ? `<a class="btn" href="/api/runs/${runId}/files/follow_up.csv">Download CSV</a>` : ""}</div></form></div>
    <div id="bulk-host"></div>
    <p class="muted small">${num(data.total)} finding${data.total === 1 ? "" : "s"}${data.total ? ` · showing ${page * size + 1}–${Math.min((page + 1) * size, data.total)}` : ""}</p>
    ${selectable && data.rows.length ? `<label class="small no-print" style="font-weight:400"><input type="checkbox" id="all" style="width:auto"> Select all on this page</label>` : ""}
    <div id="list">${data.rows.map((r) => findingItem(r, scale, reviewable, selectable)).join("") || `<div class="empty">No findings match.</div>`}</div>
    <div class="pager no-print">${page > 0 ? `<a class="btn" href="${link({ page: page - 1 })}">&larr; Previous</a>` : ""}${(page + 1) * size < data.total ? `<a class="btn" href="${link({ page: page + 1 })}">Next &rarr;</a>` : ""}</div>`;
  el.querySelector("#flt").addEventListener("submit", (ev) => {
    ev.preventDefault();
    location.hash = o.base + "?" + new URLSearchParams(Object.entries(Object.fromEntries(new FormData(ev.target).entries())).filter(([, v]) => v)).toString();
  });
  wireFindings(el.querySelector("#list"), runId, route);
  if (selectable) {
    const host = el.querySelector("#bulk-host"), sel = () => [...el.querySelectorAll(".sel:checked")].map((c) => +c.dataset.id);
    const opts = o.mode === "followup" ? DISP_FOR.cannot_determine : DISP_FOR.gap;
    const refresh = () => {
      const ids = sel();
      host.innerHTML = ids.length ? `<div class="bulk"><strong>${ids.length} selected</strong><select id="bd">${opts.map((x) => `<option value="${x}">${DISP_LABEL[x]}</option>`).join("")}</select>
        <input type="text" id="bc" placeholder="Comment (required to dispute or plan remediation)"><button id="bs">Apply to selected</button></div>` : "";
      const bs = host.querySelector("#bs");
      if (bs) bs.onclick = async () => {
        const who = needName(); if (!who) return;
        try { await post(`/api/runs/${runId}/reviews`, { finding_ids: ids, disposition: host.querySelector("#bd").value, comment: host.querySelector("#bc").value, reviewer: who }); route(); }
        catch (e) { alert(e.message); }
      };
    };
    el.querySelectorAll(".sel").forEach((c) => c.addEventListener("change", refresh));
    const all = el.querySelector("#all");
    if (all) all.addEventListener("change", () => { el.querySelectorAll(".sel").forEach((c) => (c.checked = all.checked)); refresh(); });
  }
}

/* ---------- accounts and the account file ---------- */
async function accountsTab(el, d, runId, q) {
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
  el.querySelectorAll("tr[data-acct]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/run/${runId}/account/${encodeURIComponent(tr.dataset.acct)}`)));
  el.querySelector("#af").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    location.hash = `#/run/${runId}/accounts?` + new URLSearchParams([...fd.entries()].filter(([, v]) => v)).toString();
  });
}

async function accountFile(el, d, runId, scale, account) {
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
    <div class="grid cols2" style="grid-template-columns:1.1fr 1fr;align-items:start">
      <div class="card"><h3 style="margin-top:0">Timeline (all times in UTC; source time shown beside it)</h3>${a.events.length ? `<div class="tl">${tl}</div>` : `<div class="empty">No records for this account in any source.</div>`}
        <p class="small muted">Highlighted events are cited by a finding: red for a gap, amber for cannot determine.</p></div>
      <div><h3 style="margin-top:0">Findings</h3><div id="list">${a.findings.map((f) => findingItem(f, scale, reviewable, false)).join("") || `<div class="empty">No findings for this account.</div>`}</div></div></div>`;
  wireFindings(el, runId, route);
}

/* ---------- response letter ---------- */
async function letterTab(el, d, runId) {
  const L = await api(`/api/runs/${runId}/letter`);
  let loaded = L.body;
  el.innerHTML = `
    <div class="banner ${L.status === "approved" ? "good" : "warn"}"><div class="row between"><div><strong>Response letter</strong> ${L.saved ? `<span class="badge b-${L.status}">${esc(L.status.replace("_", " "))}</span> <span class="muted small">version ${L.version} by ${esc(L.author)} on ${when(L.created_at)}</span>` : `<span class="badge b-draft">generated draft, not yet saved</span>`}</div>
      <div class="small muted">Draft → In compliance review → Approved. Approval needs every management comment written.</div></div></div>
    <div class="card no-print"><div class="row">
      <button class="primary" id="save-draft">Save draft</button><button id="to-review">Send for compliance review</button><button id="approve">Approve</button>
      <button id="regen" title="Rebuild from the latest findings, reviews and management comments">Regenerate from findings</button><button id="dl">Download .md</button><button id="pr">Print / save as PDF</button>
      ${L.versions.length ? `<select id="ver" style="width:auto"><option value="">Version history…</option>${L.versions.map((v) => `<option value="${v.version}">v${v.version} · ${esc(v.status.replace("_", " "))} · ${esc(v.author)}</option>`).join("")}</select>` : ""}
      <span id="lmsg" class="small"></span></div>
      <div id="ph" class="note" style="margin-top:10px" hidden></div></div>
    <div class="letter"><div class="no-print"><label>Edit</label><textarea id="ed" spellcheck="true"></textarea></div><div><label class="no-print">Preview</label><div class="card md" id="pv" style="max-height:none"></div></div></div>`;
  const ed = el.querySelector("#ed"), pv = el.querySelector("#pv"), msg = el.querySelector("#lmsg"), ph = el.querySelector("#ph");
  const paint = () => {
    pv.innerHTML = markdown(ed.value);
    const n = (ed.value.match(/\[To be completed[^\]]*\]/g) || []).length;
    ph.hidden = !n; ph.innerHTML = n ? `${n} management comment(s) still marked <em>[To be completed by management]</em>. Add them on the <a href="#/run/${runId}/questions">Questions</a> tab, then regenerate.` : "";
  };
  ed.value = L.body; paint(); ed.addEventListener("input", paint);
  const save = async (status) => {
    const who = needName(); if (!who) return;
    try { const r = await post(`/api/runs/${runId}/letter`, { body: ed.value, status, author: who }); msg.innerHTML = `<span class="badge b-completed">Saved as version ${r.version} (${status.replace("_", " ")})</span>`; setTimeout(route, 700); }
    catch (e) { msg.innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  };
  el.querySelector("#save-draft").onclick = () => save("draft");
  el.querySelector("#to-review").onclick = () => save("in_review");
  el.querySelector("#approve").onclick = () => { if (confirm("Approve this letter? Further edits will start a new draft version.")) save("approved"); };
  el.querySelector("#regen").onclick = async () => {
    if (!confirm("Replace the text in the editor with a fresh draft built from the latest findings and comments? Unsaved edits will be lost.")) return;
    ed.value = (await api(`/api/runs/${runId}/letter/generate`)).body; paint();
  };
  el.querySelector("#dl").onclick = () => download(`response_letter_${d.run.request_id}_${runId.slice(0, 8)}.md`, ed.value, "text/markdown");
  el.querySelector("#pr").onclick = () => window.print();
  const ver = el.querySelector("#ver");
  if (ver) ver.onchange = async () => { if (!ver.value) return; const v = await api(`/api/runs/${runId}/letter/version/${ver.value}`); ed.value = v.body; paint(); msg.textContent = `Showing version ${v.version} in the editor (not saved)`; };
}

/* ---------- evidence pack ---------- */
async function packTab(el, d, runId) {
  const { markdown: md } = await api(`/api/runs/${runId}/index`);
  const files = [["gap_report.csv", "Gap report: every gap graded by severity, with the records cited and the review decision"], ["follow_up.csv", "Items that could not be determined, to chase"],
    ["reviews.csv", "Review trail: who decided what, and when"], ["response_letter.md", "The response letter (latest saved version)"], ["rules_and_assumptions.md", "What each check tests and the interpretations applied"], ["index.md", "Index of the pack"]];
  const keys = await api("/api/gap-keys");
  el.innerHTML = `<div class="card"><div class="row between"><div><h2 style="margin:0">Evidence pack</h2><p class="muted small" style="margin:4px 0 0">Everything an auditor needs to trace each statement to a record. The pack is rebuilt from the current state every time you download it.</p></div>
    <a class="btn primary big" href="/api/runs/${runId}/pack.zip">Download full pack (.zip)</a></div>
    <h3>Contents</h3><ul>${files.map(([n, t]) => `<li><a href="/api/runs/${runId}/files/${n}">${n}</a> <span class="muted small">— ${esc(t)}</span></li>`).join("")}<li><strong>extracts/&lt;check&gt;.csv</strong> <span class="muted small">— one row per finding with its citations and extracts, per check (in the zip)</span></li></ul></div>
    <div class="card"><h2>Index</h2><div class="md">${markdown(md)}</div></div>
    <details class="card no-print"><summary style="margin:0">Quality check: score this audit against a known gap key</summary>
      <p class="muted small">If you hold the true gap list for this request, compare it to what the platform reported (target: recall ≥ 95%, false gaps &lt; 5%, no claims without a citation).</p>
      <form id="sf" class="row">${keys.length ? `<div><label>Gap key on this server</label><select name="key_name"><option value="">Choose…</option>${keys.map((k) => `<option>${esc(k)}</option>`).join("")}</select></div>` : ""}
        <div><label>…or upload one (CSV)</label><input type="file" name="file" accept=".csv"></div>
        <div><label>Account column</label><input type="text" name="account_col" value="account_id" style="width:130px"></div><div><label>Question column</label><input type="text" name="check_col" value="question_ref" style="width:130px"></div>
        <div style="align-self:flex-end"><button class="primary">Score</button></div></form><div id="sr"></div></details>`;
  el.querySelector("#sf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = el.querySelector("#sr"); out.innerHTML = `<p class="muted">Scoring…</p>`;
    try {
      const s = await api(`/api/runs/${runId}/score`, { method: "POST", body: new FormData(ev.target) });
      const row = (l, v, ok, t) => `<tr><td>${l}</td><td class="num"><strong>${v}</strong></td><td><span class="badge ${ok ? "b-completed" : "b-failed"}">${ok ? "PASS" : "FAIL"}</span></td><td class="muted">${t}</td></tr>`;
      const list = (t, a) => (a.length ? `<h3>${t} (${a.length})</h3><p class="mono small">${a.slice(0, 40).map((x) => esc(x.join(" · "))).join("<br>")}</p>` : "");
      out.innerHTML = `<table style="margin-top:14px"><thead><tr><th>Measure</th><th class="num">Result</th><th></th><th>Target</th></tr></thead><tbody>
        ${row("Gap recall", (s.recall * 100).toFixed(1) + `% (${s.matched}/${s.true_gaps})`, s.recall >= 0.95, "≥ 95%")}${row("False-gap rate", (s.false_gap_rate * 100).toFixed(1) + `% (${s.false_gaps.length}/${s.reported_gaps})`, s.false_gap_rate < 0.05, "< 5%")}
        ${row("Claims without a citation", s.unsupported_claims, s.unsupported_claims === 0, "0")}</tbody></table>${list("Missed gaps", s.missed)}${list("False gaps", s.false_gaps)}`;
    } catch (e) { out.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  });
}

/* ---------- rules and data ---------- */
async function rulesPage(el, standalone, runId, done) {
  const [r, src] = await Promise.all([api("/api/rules"), api("/api/data-sources")]);
  const pol = {}; r.policy.forEach((p) => (pol[p.rule_key] ||= []).push(p));
  const lim = (keys) => (keys || []).map((k) => pol[k] ? `${esc(k.replace(/_/g, " "))}: ` + pol[k].map((p) => `<strong>${esc(p.rule_value)}</strong> ${esc(p.unit || "")} <span class="muted">(${p.effective_to ? `${fdate(p.effective_from)} to ${fdate(p.effective_to)}` : `from ${fdate(p.effective_from)}`})</span>`).join(", ") : "").filter(Boolean).join("<br>");
  el.innerHTML = `${standalone ? `<h1>Rules &amp; data ${help("data")}</h1><p class="muted">How results are decided, the limits in force, the interpretations the platform applies, and what data it reads. Use this to defend a result to the lender.</p>` : ""}
    <div class="card"><h2>How to read a result</h2><table><tbody>${Object.entries(r.status_meaning).map(([k, v]) => `<tr><td style="width:170px">${badge(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><h2>What each check tests</h2><table><thead><tr><th>Check</th><th>Passes when</th><th>Gap when</th><th>Limits in force (D12)</th><th>Sources</th></tr></thead><tbody>
      ${Object.entries(r.checks).filter(([k]) => k !== "other").map(([k, i]) => `<tr><td><strong>${esc(i.title)}</strong><div class="small muted mono">${esc(k)}</div></td><td>${esc(i.tests)}</td><td>${esc(i.gap)}${i.unknown && !/^None|^n\/a/.test(i.unknown) ? `<div class="small muted">Cannot determine: ${esc(i.unknown)}</div>` : ""}</td><td class="small">${lim(i.limits) || "—"}</td><td class="small">${(i.sources || []).map(esc).join(", ")}</td></tr>`).join("")}</tbody></table></div>
    <div class="card"><h2>Assumptions applied</h2><ul>${r.assumptions.map((a) => `<li><strong>${esc(a.topic)}.</strong> ${esc(a.text)}</li>`).join("")}</ul>
      <p class="small muted">These are the platform's current interpretations. If your engagement requires a different one, tell the platform owners before relying on the result.</p></div>
    <div class="card"><h2>Data the platform reads</h2><table><thead><tr><th>Source</th><th class="num">Records</th><th>From</th><th>To</th><th>Source time zone</th></tr></thead><tbody>
      ${src.map((s) => `<tr><td>${esc(s.source)}</td><td class="num">${num(s.rows)}</td><td class="small">${s.first ? esc(String(s.first).slice(0, 10)) : "—"}</td><td class="small">${s.last ? esc(String(s.last).slice(0, 10)) : "—"}</td><td class="small">${esc(s.timezone)}</td></tr>`).join("")}</tbody></table>
      <p class="small muted">Every timestamp is compared in UTC; the original value is shown beside it wherever it is cited.</p></div>`;
}

/* ---------- source record viewer ---------- */
async function showRecord(table, key) {
  const m = document.getElementById("modal");
  m.hidden = false; m.innerHTML = `<div class="box"><p class="muted">Loading…</p></div>`;
  m.onclick = (e) => { if (e.target === m) m.hidden = true; };
  try {
    const r = await api(`/api/record?table=${encodeURIComponent(table)}&key=${encodeURIComponent(key)}`);
    m.innerHTML = `<div class="box"><div class="row between"><h2 style="margin:0">Source record</h2><button id="close">Close</button></div>
      <p class="muted small mono">${esc(r.table)} · ${esc(r.key_column)} = ${esc(key)}</p>
      ${(r.rows || [r.record]).map((row, i) => `${r.rows && r.rows.length > 1 ? `<h3>Row ${i + 1} of ${r.rows.length}${row.call_status ? ` · ${esc(row.call_status)}` : ""}</h3>` : ""}<dl class="kv">${Object.entries(row).map(([k, v]) => `<dt>${esc(k)}</dt><dd class="mono">${esc(v)}</dd>`).join("")}</dl>`).join("")}
      <p class="small muted">Exactly as held in the source table, in the source's own time zone. A call session has one row per status event.</p></div>`;
  } catch (e) { m.innerHTML = `<div class="box"><div class="err">${esc(e.message)}</div><button id="close">Close</button></div>`; }
  document.getElementById("close").onclick = () => (m.hidden = true);
}

/* ---------- advanced: data explorer ---------- */
const SAMPLES = [
  ["Rows per source", `SELECT 'Call sessions' AS source, count(*) AS rows FROM staging.call_sessions
UNION ALL SELECT 'Messages', count(*) FROM staging.messages
UNION ALL SELECT 'Consents', count(*) FROM staging.consents
UNION ALL SELECT 'Recordings', count(*) FROM staging.recordings
UNION ALL SELECT 'Transcript segments', count(*) FROM staging.transcript_segments
UNION ALL SELECT 'Notices', count(*) FROM staging.notices`],
  ["Calls after the window closes (rule in force that day)", `SELECT s.account_id, s.session_key, s.started_ts_src, s.started_ts_src_tz, (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::time AS local_time, r.rule_value AS window_end
FROM staging.call_sessions s JOIN staging.policy_rules r ON r.rule_key = 'calling_window_end'
 AND (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date >= r.effective_from AND ((s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date < r.effective_to OR r.effective_to IS NULL)
WHERE s.counts_as_attempt AND NOT s.is_mirror_duplicate AND (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::time >= r.rule_value::time ORDER BY s.started_ts_utc LIMIT 50`],
  ["Contact numbers called over the cap in a day", `SELECT contact_no, (started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date AS day, count(*) AS attempts
FROM staging.call_sessions WHERE counts_as_attempt AND NOT is_mirror_duplicate GROUP BY 1, 2 HAVING count(*) >= 5 ORDER BY attempts DESC, day LIMIT 50`],
  ["Sessions logged by both dialers (mirrors)", `SELECT account_id, session_key, mirror_of, started_ts_src, started_ts_src_tz FROM staging.call_sessions WHERE is_mirror_duplicate ORDER BY started_ts_utc LIMIT 50`],
  ["Connected calls the recording store cannot confirm", `SELECT s.account_id, s.session_key, r.storage_status, r.note FROM staging.call_sessions s
JOIN staging.recordings r ON r.session_key = s.session_key WHERE s.connected AND r.storage_status <> 'AVAILABLE' ORDER BY s.started_ts_utc LIMIT 50`],
];
async function sqlPage() {
  app.innerHTML = `<h1>Data explorer</h1><p class="muted">For analysts: run a read-only SELECT against the loaded data (staging views are in UTC). Same read-only warehouse tool the agent uses.</p>
    <div class="card"><div class="row"><div style="flex:1;min-width:240px"><label for="samp">Sample queries</label><select id="samp">${SAMPLES.map(([n], i) => `<option value="${i}">${esc(n)}</option>`).join("")}</select></div>
      <div style="align-self:flex-end"><button class="primary" id="go">Run query</button></div></div>
      <label for="q" style="margin-top:12px">Query</label><textarea id="q" spellcheck="false" style="min-height:160px"></textarea></div><div id="res"></div>`;
  const q = document.getElementById("q"), samp = document.getElementById("samp");
  const run = async () => {
    const res = document.getElementById("res"); res.innerHTML = `<div class="card muted">Running…</div>`;
    try {
      const r = await post("/api/sql", { query: q.value });
      res.innerHTML = `<div class="card"><div class="muted small">${num(r.rows.length)} rows${r.truncated ? " (truncated)" : ""}</div>${r.rows.length ? `<div style="overflow:auto;max-height:520px"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">No rows.</div>`}</div>`;
    } catch (e) { res.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  samp.onchange = () => { q.value = SAMPLES[+samp.value][1]; run(); };
  document.getElementById("go").onclick = run; q.value = SAMPLES[0][1]; run();
}


/* ---------- knowledge base ---------- */
const SAMPLE_CIRCULAR = `1. Calling hours: collection calls to borrowers may be made only between 8:00 a.m. and 6:50 p.m. local time.

2. Not more than five attempts per day shall be made to the same contact number, whether by manual or campaign dialing.

3. Notices shall be dispatched within three working days and served within seven working days of the default trigger.

4. Recovery agents must hold a valid certification on the date of every call.

5. The borrower's identity must be verified before any dues are disclosed on a call.

6. Prior consent is required before sending any WhatsApp or SMS message for collections.

7. All collection calls shall be recorded and recordings retained for twelve months.`;

async function kbPage() {
  const docs = await api("/api/kb");
  app.innerHTML = `<h1>Knowledge base ${help("guardrails")}</h1>
    <p class="muted">The circulars, policies and SOPs that guardrails come from. Upload one, split it into clauses, and turn each testable obligation into a guardrail linked to its clause.</p>
    <div class="card"><h2>Documents</h2>
      ${docs.length ? `<table><thead><tr><th>Document</th><th>Type</th><th>Reference</th><th>Effective</th><th class="num">Clauses</th><th class="num">Guardrails</th></tr></thead><tbody>
        ${docs.map((d) => `<tr class="click" data-doc="${d.doc_id}"><td><strong>${esc(d.title)}</strong><div class="small muted">${esc(d.issuer || "")} · added by ${esc(d.uploaded_by)}</div></td><td>${esc(d.doc_type)}</td><td>${esc(d.reference_no || "—")}</td><td class="small">${d.effective_date ? fdate(d.effective_date) : "—"}</td><td class="num">${num(d.clauses)}</td><td class="num">${num(d.guardrails)}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">No documents yet. Add one below.</div>`}</div>
    <div class="card"><h2>Add a document</h2><form id="kbf">
      <div class="grid cols2">
        <div><label>Title</label><input type="text" name="title" required placeholder="e.g. Fair practices on recovery calls"></div>
        <div><label>Type</label><select name="doc_type"><option value="circular">Circular</option><option value="policy">Lender policy</option><option value="sop">Approved SOP</option></select></div>
        <div><label>Issuer</label><input type="text" name="issuer" placeholder="Regulator or lender"></div>
        <div><label>Reference number</label><input type="text" name="reference_no"></div>
        <div><label>Effective from</label><input type="date" name="effective_date"></div>
        <div><label>File (PDF or text)</label><input type="file" name="file" accept=".pdf,.txt,.md"></div></div>
      <div style="margin-top:12px"><div class="row between"><label>…or paste the text</label><button type="button" class="link" id="kbsample">Use a sample circular</button></div><textarea name="text" id="kbtext" placeholder="Numbered clauses, one obligation each, work best."></textarea></div>
      <div class="row" style="margin-top:12px"><button class="primary">Add document</button><span id="kberr"></span></div></form></div>`;
  app.querySelectorAll("tr[data-doc]").forEach((tr) => tr.addEventListener("click", () => (location.hash = `#/kb/${tr.dataset.doc}`)));
  document.getElementById("kbsample").onclick = () => {
    document.getElementById("kbtext").value = SAMPLE_CIRCULAR;
    const f = document.getElementById("kbf"); f.title.value = "Sample: fair practices on collection calls (synthetic)"; f.issuer.value = "Example Regulator"; f.reference_no.value = "SYN/2026/04"; f.effective_date.value = "2026-04-01";
  };
  document.getElementById("kbf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const who = needName(); if (!who) return;
    const fd = new FormData(ev.target); fd.append("uploaded_by", who);
    try { const r = await api("/api/kb", { method: "POST", body: fd }); location.hash = `#/kb/${r.doc_id}`; }
    catch (e) { document.getElementById("kberr").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  });
}

async function kbDocPage(id) {
  const d = await api(`/api/kb/${id}`);
  const byClause = {};
  d.guardrails.forEach((g) => (byClause[g.source_clause] ||= []).push(g));
  app.innerHTML = `<p class="small"><a href="#/kb">&larr; Knowledge base</a></p>
    <div class="row between"><div><h1>${esc(d.doc.title)}</h1><div class="muted small">${esc(d.doc.doc_type)}${d.doc.issuer ? ` · ${esc(d.doc.issuer)}` : ""}${d.doc.reference_no ? ` · ${esc(d.doc.reference_no)}` : ""}${d.doc.effective_date ? ` · effective ${fdate(d.doc.effective_date)}` : ""} · added by ${esc(d.doc.uploaded_by)}</div></div>
      <div class="row"><button class="primary" id="sg">Suggest guardrails from the clauses</button><a class="btn" href="#/guardrails">Open guardrails</a></div></div>
    <p id="sgmsg" class="small muted"></p>
    <div class="card"><h2>Clauses</h2>${d.clauses.map((c) => `<div style="padding:10px 0;border-bottom:1px solid var(--border)"><div class="row"><span class="tag">${esc(c.clause_no)}</span><div style="flex:1;min-width:260px">${esc(c.body)}</div></div>
      ${(byClause[c.clause_no] || []).map((g) => `<div class="small" style="margin:6px 0 0 44px"><span class="badge b-${g.status === "published" ? "completed" : "draft"}">${esc(g.status)}</span> guardrail <a href="#/guardrails?edit=${g.guardrail_id}">${esc(g.title)}</a> · ${esc(g.check_type.replace(/_/g, " "))}${g.parameters && Object.keys(g.parameters).length ? ` · <span class="mono">${esc(JSON.stringify(g.parameters))}</span>` : ""}</div>`).join("")}</div>`).join("")}</div>`;
  document.getElementById("sg").onclick = async () => {
    const who = needName(); if (!who) return;
    const r = await post(`/api/kb/${id}/suggest`, { by: who }).catch((e) => ({ err: e.message }));
    if (r.err) { document.getElementById("sgmsg").textContent = r.err; return; }
    document.getElementById("sgmsg").textContent = r.created ? `${r.created} draft guardrail(s) created. Review and publish them on the Guardrails page.` : "No new guardrails: every testable clause already has one.";
    if (r.created) setTimeout(route, 900);
  };
}

/* ---------- guardrails ---------- */
const WEIGHT_HELP = { 1: "Normal review order", 2: "Elevated: reviewed earlier", 3: "Highest priority: reviewed first" };
async function guardrailsPage(q) {
  const [list, docs] = await Promise.all([api("/api/guardrails"), api("/api/kb")]);
  const tab = q.show || "all";
  const shown = list.filter((g) => tab === "all" || g.status === tab);
  app.innerHTML = `<div class="row between"><div><h1>Guardrails ${help("guardrails")}</h1>
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
    try { await post(g ? `/api/guardrails/${g.guardrail_id}/versions` : "/api/guardrails", body); m.hidden = true; route(); }
    catch (e) { document.getElementById("gerr").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  });
}


/* ---------- guide ---------- */
function guidePage(topic) {
  const t = GUIDE.find((x) => x.id === topic) || GUIDE[0];
  try { localStorage.setItem("seenGuide", "1"); } catch (_) {}
  app.innerHTML = `<div class="guide"><nav class="toc no-print">${GUIDE.map((x) => `<a href="#/guide/${x.id}" class="${x.id === t.id ? "active" : ""}">${esc(x.title)}</a>`).join("")}</nav>
    <div class="doc">${t.html}
      <div class="row between no-print" style="margin-top:22px;padding-top:12px;border-top:1px solid var(--border)">
        ${GUIDE.indexOf(t) > 0 ? `<a href="#/guide/${GUIDE[GUIDE.indexOf(t) - 1].id}">&larr; ${esc(GUIDE[GUIDE.indexOf(t) - 1].title)}</a>` : "<span></span>"}
        ${GUIDE.indexOf(t) < GUIDE.length - 1 ? `<a href="#/guide/${GUIDE[GUIDE.indexOf(t) + 1].id}">${esc(GUIDE[GUIDE.indexOf(t) + 1].title)} &rarr;</a>` : "<span></span>"}</div></div></div>`;
}

/* ================= boot ================= */
(async () => {
  document.getElementById("who").addEventListener("click", () => {
    const n = (window.prompt("Your name:", reviewer()) || "").trim();
    if (n) setReviewer(n);
  });
  renderWho();
  try {
    [state.config, state.rules] = await Promise.all([api("/api/config"), api("/api/rules")]);
    document.getElementById("parser-badge").textContent = state.config.parser === "llm" ? `Request reader: ${state.config.model}` : "Request reader: keyword fallback (no AI key set)";
  } catch (_) {}
  route();
})();
