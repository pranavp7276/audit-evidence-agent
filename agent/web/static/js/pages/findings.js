import { STATUS_LABEL, api, post, esc, num, help, badge, sevBadge, info, needName, navigate, refresh } from "../core.js";

/* ---------- findings (shared by questions, gap register, follow-up, account file) ---------- */
const DISP_LABEL = { open: "Open", confirmed: "Confirmed", disputed: "Disputed", remediation_planned: "Remediation planned", evidence_obtained: "Evidence obtained" };
const DISP_FOR = { gap: ["open", "confirmed", "disputed", "remediation_planned"], cannot_determine: ["open", "evidence_obtained"] };
const dispBadge = (d) => `<span class="badge b-${esc(d)}">${esc(DISP_LABEL[d] || d)}</span>`;

export function findingItem(f, scale, reviewable, selectable) {
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

export function wireFindings(root, runId, onSaved) {
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

export async function findingsPage(el, d, runId, scale, o) {
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
    navigate(o.base + "?" + new URLSearchParams(Object.entries(Object.fromEntries(new FormData(ev.target).entries())).filter(([, v]) => v)).toString());
  });
  wireFindings(el.querySelector("#list"), runId, refresh);
  if (selectable) {
    const host = el.querySelector("#bulk-host"), sel = () => [...el.querySelectorAll(".sel:checked")].map((c) => +c.dataset.id);
    const opts = o.mode === "followup" ? DISP_FOR.cannot_determine : DISP_FOR.gap;
    const paintBulk = () => {
      const ids = sel();
      host.innerHTML = ids.length ? `<div class="bulk"><strong>${ids.length} selected</strong><select id="bd">${opts.map((x) => `<option value="${x}">${DISP_LABEL[x]}</option>`).join("")}</select>
        <input type="text" id="bc" placeholder="Comment (required to dispute or plan remediation)"><button id="bs">Apply to selected</button></div>` : "";
      const bs = host.querySelector("#bs");
      if (bs) bs.onclick = async () => {
        const who = needName(); if (!who) return;
        try { await post(`/api/runs/${runId}/reviews`, { finding_ids: ids, disposition: host.querySelector("#bd").value, comment: host.querySelector("#bc").value, reviewer: who }); refresh(); }
        catch (e) { alert(e.message); }
      };
    };
    el.querySelectorAll(".sel").forEach((c) => c.addEventListener("change", paintBulk));
    const all = el.querySelector("#all");
    if (all) all.addEventListener("change", () => { el.querySelectorAll(".sel").forEach((c) => (c.checked = all.checked)); paintBulk(); });
  }
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
