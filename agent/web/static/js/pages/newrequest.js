import { app, state, api, esc, num, help, info, needName, navigate } from "../core.js";

const draft = { form: {}, preview: null };

export async function newRequestPage() {
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
      ${p.parser_note ? `<div class="note"><strong>Models not used.</strong> ${esc(p.parser_note)}</div>` : ""}
      ${p.checks.length ? "" : `<div class="err">No checks could be made from this text. Describe what to test (for example “check consent, calling hours and verification for accounts contacted last month”) or paste numbered questions.</div>`}
      ${p.instruction ? `<div class="note">Your request is an instruction rather than numbered questions, so the platform chose ${p.checks.length} guardrail check(s) to test${p.checks.length === 7 ? " (a full compliance audit: every guardrail listed in Rules &amp; data)" : ""}. Severities use the default scale ${p.scale.map(esc).join(" › ")} because the request gave none. Change anything below before running.</div>` : ""}
      <p class="muted">${p.instruction ? `Guardrails to test: ${p.checks.length}.` : `${questions} question(s) became ${p.checks.length} check(s)${p.parser === "models" ? ` by the models (${esc(p.models.decision)} decides each question, ${esc(p.models.reasoning)} splits bundled ones); please check each row` : " by the keyword reader (no model is set up), so please check each row"}.`}
        Questions can be vague or bundle several tests: change the test, set the severity from the request's scale, or split a bundled question. A question that fits no test is reported as <em>unanswered</em>, never dropped.</p>
      <table class="wiz"><thead><tr><th>Check</th><th>Question as written</th><th>Test applied</th><th>Severity</th><th></th></tr></thead><tbody>
      ${p.checks.map((c, i) => `<tr data-i="${i}"><td><input type="text" data-f="check_id" value="${esc(c.check_id)}" style="width:70px"><div class="small muted">${esc(c.question_ref)}</div></td>
        <td>${esc(c.question_text)}${c.reader ? `<div class="small ${c.confidence != null && c.confidence < 0.7 ? "" : "muted"}" style="${c.confidence != null && c.confidence < 0.7 ? "color:var(--unk);font-weight:700" : ""}">Read by ${esc(c.reader)}${c.confidence != null && c.confidence < 0.7 ? " · low confidence, please check" : ""}</div>` : ""}</td>
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
      navigate(`#/run/${r.run_id}`);
    } catch (e) { document.getElementById("run-err").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; btn.disabled = false; btn.textContent = "Run audit"; }
  });
  el.scrollIntoView({ behavior: "smooth" });
}
