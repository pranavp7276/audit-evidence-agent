import { app, state, api, post, esc, num, when, fdate, subnav, sevBadge, navigate, needName, refresh } from "../core.js";

/* Issues: confirmed gaps tracked to closure. An issue points at gaps and never changes them. */

const LABEL = { open: "Open", in_progress: "In progress", resolved: "Resolved, awaiting verification", verified: "Verified and closed", wont_fix: "Will not fix" };
const CLS = { open: "b-failed", in_progress: "b-in_review", resolved: "b-cannot_determine", verified: "b-completed", wont_fix: "b-draft" };
const NAME = (k) => (state.config.check_types && state.config.check_types[k]) || (k || "").replace(/_/g, " ") || "Mixed tests";
const SCALE = ["Critical", "Major", "Minor"];
const chip = (s) => `<span class="badge ${CLS[s]}">${esc(LABEL[s])}</span>`;
const NEEDS_NOTE = { resolved: "How was it resolved? (what changed, and where the evidence is)", wont_fix: "Why will this not be fixed?" };

export async function issuesPage(q) {
  const params = new URLSearchParams(); ["status", "owner"].forEach((k) => q[k] && params.set(k, q[k])); if (q.overdue) params.set("overdue", "true");
  const data = await api(`/api/issues?${params}`);
  const c = data.counts, n = (...ks) => ks.reduce((a, k) => a + (c[k] || 0), 0);
  const overdueAll = (await api("/api/issues?overdue=true")).rows.length;
  const here = q.overdue ? "#/issues?overdue=1" : q.status ? `#/issues?status=${q.status}` : "#/issues";
  app.innerHTML = `
    <div class="row between"><div><h1>Issues</h1><p class="muted" style="max-width:70ch">Confirmed gaps being tracked to closure: who owns each, when it is due, and what closed it. Raise one from <a href="#/exceptions">Exceptions</a>. Fixing a gap happens outside this platform; an issue records where it stands.</p></div>
      <a class="btn" href="/api/issues.csv">Download register (CSV)</a></div>
    ${subnav([["#/issues", "All", n(...Object.keys(c))], ["#/issues?status=active", "Active", n("open", "in_progress", "resolved")], ["#/issues?overdue=1", "Overdue", overdueAll],
      ["#/issues?status=resolved", "Awaiting verification", n("resolved")], ["#/issues?status=verified", "Closed", n("verified", "wont_fix")]], here)}
    <div class="card" style="padding:0"><table><thead><tr><th class="num">#</th><th>Issue</th><th>Severity</th><th>Owner</th><th>Due</th><th>Status</th><th class="num">Gaps</th></tr></thead><tbody>
    ${data.rows.map((i) => `<tr class="click" data-id="${i.issue_id}"><td class="num">${i.issue_id}</td><td><strong>${esc(i.title)}</strong><div class="small muted">${esc(NAME(i.check_type))}</div></td>
      <td>${i.severity ? sevBadge(i.severity, SCALE) : ""}</td><td class="small">${esc(i.owner || "—")}</td>
      <td class="small">${i.due_date ? fdate(i.due_date) : "—"}${i.overdue ? ` <span class="badge b-failed">overdue</span>` : ""}</td><td>${chip(i.status)}</td><td class="num">${num(i.findings)}</td></tr>`).join("")
      || `<tr><td colspan="7"><div class="empty">No issues here. Select gaps on the <a href="#/exceptions">Exceptions</a> page to raise one.</div></td></tr>`}
    </tbody></table></div>`;
  app.querySelectorAll("tr[data-id]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/issues/${tr.dataset.id}`)));
}

export async function issueDetailPage(id) {
  const i = await api(`/api/issues/${id}`);
  const act = async (body) => { const who = needName(); if (!who) return; try { await post(`/api/issues/${id}`, { ...body, actor: who }); refresh(); } catch (e) { alert(e.message); } };
  app.innerHTML = `
    <p class="small"><a href="#/issues">&larr; All issues</a></p>
    <div class="row between"><h1>#${i.issue_id} ${esc(i.title)} ${chip(i.status)}</h1></div>
    <div class="muted small">${esc(NAME(i.check_type))}${i.severity ? ` · ${esc(i.severity)}` : ""} · raised by ${esc(i.created_by)} ${when(i.created_at)} · ${num(i.findings)} gap${i.findings === 1 ? "" : "s"}${i.overdue ? ` · <span style="color:var(--gap);font-weight:700">overdue</span>` : ""}</div>
    ${i.description ? `<p>${esc(i.description)}</p>` : ""}
    <div class="grid cols2" style="margin-top:12px;align-items:start">
      <div class="card"><h3 style="margin-top:0">Owner and due date</h3>
        <div class="row"><div><label for="ow">Owner</label><input id="ow" type="text" value="${esc(i.owner || "")}"></div><div><label for="du">Due</label><input id="du" type="date" value="${esc(i.due_date ? String(i.due_date).slice(0, 10) : "")}"></div>
        <div style="align-self:flex-end"><button id="sv">Save</button></div></div>
        <h3>Status</h3>
        ${i.next_statuses.length ? `<div class="row">${i.next_statuses.map((s) => `<button data-s="${s}" class="${s === "verified" ? "primary" : ""}">Mark ${esc(LABEL[s].toLowerCase())}</button>`).join("")}</div>
          <div id="nw" hidden style="margin-top:8px"><label for="nt" id="nl"></label><textarea id="nt" rows="2"></textarea><button class="primary" id="ns" style="margin-top:6px">Save</button></div>
          ${i.status === "resolved" ? `<p class="small muted">A different person from the one who resolved it has to verify it.</p>` : ""}` : `<p class="muted small">This issue is closed.</p>`}
        <h3>Add a note</h3><div class="row"><input id="nn" type="text" style="flex:1" placeholder="e.g. Agency has switched off the dialler's out-of-hours setting"><button id="na">Add</button></div></div>
      <div class="card"><h3 style="margin-top:0">History</h3><ol class="hist">${i.events.map((e) => `<li><strong>${esc(e.actor)}</strong> <span class="muted small">${when(e.created_at)}</span><div>${({ created: "Raised the issue", status: `Status: ${esc(LABEL[e.body] || e.body)}`, owner: `Owner: ${esc(e.body)}`, due: `Due: ${esc(e.body)}`, note: esc(e.body) })[e.kind]}${e.kind === "created" ? ` ${esc(e.body)}` : ""}</div></li>`).join("")}</ol></div></div>
    <div class="card"><h3 style="margin-top:0">Gaps in this issue</h3><table><thead><tr><th>Audit</th><th>Account</th><th>What was found</th></tr></thead><tbody>
      ${i.gaps.map((g) => `<tr class="click" data-run="${g.run_id}" data-acct="${esc(g.account_id)}"><td><strong>${esc(g.request_id)}</strong> ${esc(g.question_ref)}</td><td class="mono small">${esc(g.account_number || g.account_id)}</td><td class="small">${esc(g.reason)}</td></tr>`).join("")}</tbody></table></div>`;
  app.querySelector("#sv").onclick = () => act({ owner: app.querySelector("#ow").value, due: app.querySelector("#du").value || undefined });
  app.querySelector("#na").onclick = () => { const t = app.querySelector("#nn").value.trim(); if (t) act({ note: t }); };
  let pending = null;
  app.querySelectorAll("[data-s]").forEach((b) => b.addEventListener("click", () => {
    pending = b.dataset.s;
    if (NEEDS_NOTE[pending]) { app.querySelector("#nw").hidden = false; app.querySelector("#nl").textContent = NEEDS_NOTE[pending]; app.querySelector("#nt").focus(); }
    else act({ status: pending });
  }));
  const ns = app.querySelector("#ns"); if (ns) ns.onclick = () => act({ status: pending, note: app.querySelector("#nt").value });
  app.querySelectorAll("tr[data-acct]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/run/${tr.dataset.run}/account/${encodeURIComponent(tr.dataset.acct)}`)));
}
