import { api, post, esc, when, needName, markdown, download, refresh } from "../core.js";

export async function letterTab(el, d, runId) {
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
    try { const r = await post(`/api/runs/${runId}/letter`, { body: ed.value, status, author: who }); msg.innerHTML = `<span class="badge b-completed">Saved as version ${r.version} (${status.replace("_", " ")})</span>`; setTimeout(refresh, 700); }
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
