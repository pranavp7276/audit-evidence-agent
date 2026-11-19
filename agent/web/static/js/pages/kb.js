import { app, api, post, esc, num, help, fdate, needName, navigate, refresh } from "../core.js";

const SAMPLE_CIRCULAR = `1. Calling hours: collection calls to borrowers may be made only between 8:00 a.m. and 6:50 p.m. local time.

2. Not more than five attempts per day shall be made to the same contact number, whether by manual or campaign dialing.

3. Notices shall be dispatched within three working days and served within seven working days of the default trigger.

4. Recovery agents must hold a valid certification on the date of every call.

5. The borrower's identity must be verified before any dues are disclosed on a call.

6. Prior consent is required before sending any WhatsApp or SMS message for collections.

7. All collection calls shall be recorded and recordings retained for twelve months.`;

export async function kbPage() {
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
  app.querySelectorAll("tr[data-doc]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/kb/${tr.dataset.doc}`)));
  document.getElementById("kbsample").onclick = () => {
    document.getElementById("kbtext").value = SAMPLE_CIRCULAR;
    const f = document.getElementById("kbf"); f.title.value = "Sample: fair practices on collection calls (synthetic)"; f.issuer.value = "Example Regulator"; f.reference_no.value = "SYN/2026/04"; f.effective_date.value = "2026-04-01";
  };
  document.getElementById("kbf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const who = needName(); if (!who) return;
    const fd = new FormData(ev.target); fd.append("uploaded_by", who);
    try { const r = await api("/api/kb", { method: "POST", body: fd }); navigate(`#/kb/${r.doc_id}`); }
    catch (e) { document.getElementById("kberr").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  });
}

export async function kbDocPage(id) {
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
    if (r.created) setTimeout(refresh, 900);
  };
}
