import { app, state, api, post, esc, num, badge, sevBadge, navigate, needName } from "../core.js";

/* Every gap and every open question across the audits, most serious first. Gaps can be selected and raised as an issue. */

const SCALE = ["Critical", "Major", "Minor"];
const SECOND = { disputes: ["b-failed", "Second reading disagrees"], unclear: ["b-cannot_determine", "Second reading unsure"] };
const NAME = (k) => (state.config.check_types && state.config.check_types[k]) || k.replace(/_/g, " ");
const KEYS = ["status", "check_type", "run", "disposition", "issue", "challenge", "text", "account"];

export async function exceptionsPage(q) {
  const page = +(q.page || 0), size = 50;
  const params = new URLSearchParams({ limit: size, offset: page * size });
  KEYS.forEach((k) => q[k] && params.set(k, q[k]));
  const data = await api(`/api/exceptions?${params}`);
  const link = (over) => "#/exceptions?" + new URLSearchParams(Object.entries({ ...q, ...over }).filter(([, v]) => v !== "" && v != null)).toString();
  const sel = (name, label, opts) => `<div><label>${label}</label><select name="${name}">${opts.map(([v, t]) => `<option value="${esc(v)}" ${String(q[name] || "") === String(v) ? "selected" : ""}>${esc(t)}</option>`).join("")}</select></div>`;
  const csvParams = new URLSearchParams(); KEYS.forEach((k) => q[k] && csvParams.set(k, q[k]));
  app.innerHTML = `
    <h1>Exceptions</h1>
    <p class="muted">Every reported gap and every open question across your audits, most serious first, with the second reading's view beside it. Select gaps to raise an issue and track them to closure.</p>
    <div class="card no-print"><form id="ef" class="row">
      ${sel("status", "Kind", [["", "Gaps and open questions"], ["gap", "Gaps"], ["cannot_determine", "Cannot determine"]])}
      ${sel("check_type", "Test", [["", "All tests"], ...data.check_types.map((c) => [c.check_type, `${NAME(c.check_type)} (${num(c.n)})`])])}
      ${sel("run", "Audit", [["", "All audits"], ...data.runs.map((r) => [r.run_id, r.request_id])])}
      ${sel("disposition", "Review", [["", "Any"], ["open", "Not yet reviewed"], ["confirmed", "Confirmed"], ["disputed", "Disputed"], ["remediation_planned", "Remediation planned"], ["evidence_obtained", "Evidence obtained"]])}
      ${sel("issue", "Issue", [["", "Any"], ["none", "No issue raised"], ["open", "In an open issue"]])}
      ${sel("challenge", "Second reading", [["", "Any"], ["flagged", "Disagrees or unsure"]])}
      <div style="flex:1;min-width:140px"><label>Loan account contains</label><input type="search" name="account" value="${esc(q.account || "")}" placeholder="CNF123456789"></div>
      <div style="align-self:flex-end" class="row"><button class="primary">Filter</button><a class="btn" href="/api/exceptions.csv?${csvParams}">Download CSV</a></div></form>
      ${q.text ? `<p class="small" style="margin:8px 0 0">Containing <strong>“${esc(q.text)}”</strong> <a href="${link({ text: "", page: 0 })}">clear</a></p>` : ""}</div>
    <div id="bulk"></div>
    <p class="muted small">${num(data.total)} exception${data.total === 1 ? "" : "s"}${data.total ? ` · showing ${page * size + 1}–${Math.min((page + 1) * size, data.total)}` : ""}</p>
    <div class="card" style="padding:0"><table><thead><tr><th style="width:30px"></th><th>Audit · test</th><th>Account</th><th>What was found</th><th>Review</th><th>Issue</th></tr></thead><tbody>
      ${data.rows.map((r) => `<tr class="click" data-run="${r.run_id}" data-acct="${esc(r.account_id)}">
        <td>${r.status === "gap" && !r.issue_id ? `<input type="checkbox" class="sel" value="${r.finding_id}" data-run="${esc(r.request_id)}" data-test="${esc(r.check_type)}" data-sev="${esc(r.severity || "")}" style="width:auto">` : ""}</td>
        <td><strong>${esc(r.request_id)}</strong> ${esc(r.question_ref)}<div class="small muted">${esc(NAME(r.check_type))}</div></td>
        <td class="mono small">${esc(r.account_number || r.account_id)}</td>
        <td><div>${badge(r.status)} ${r.severity ? sevBadge(r.severity, SCALE) : ""} ${SECOND[r.challenge_verdict] ? `<span class="badge ${SECOND[r.challenge_verdict][0]}">${SECOND[r.challenge_verdict][1]}</span>` : ""}</div><div class="small">${esc(r.reason)}</div></td>
        <td class="small">${esc(r.disposition.replace(/_/g, " "))}</td>
        <td class="small">${r.issue_id ? `<a href="#/issues/${r.issue_id}">Issue #${r.issue_id}</a>` : `<span class="muted">none</span>`}</td></tr>`).join("") || `<tr><td colspan="6"><div class="empty">No exceptions match.</div></td></tr>`}
    </tbody></table></div>
    <div class="pager no-print">${page > 0 ? `<a class="btn" href="${link({ page: page - 1 })}">&larr; Previous</a>` : ""}${(page + 1) * size < data.total ? `<a class="btn" href="${link({ page: page + 1 })}">Next &rarr;</a>` : ""}</div>`;
  app.querySelector("#ef").addEventListener("submit", (ev) => {
    ev.preventDefault();
    navigate("#/exceptions?" + new URLSearchParams([...new FormData(ev.target).entries(), ...(q.text ? [["text", q.text]] : [])].filter(([, v]) => v)).toString());
  });
  app.querySelectorAll("tr[data-acct]").forEach((tr) => tr.addEventListener("click", (e) => { if (!e.target.closest("input,a,button")) navigate(`#/run/${tr.dataset.run}/account/${encodeURIComponent(tr.dataset.acct)}`); }));
  const bulk = app.querySelector("#bulk"), chosen = () => [...app.querySelectorAll(".sel:checked")];
  const paint = () => {
    const c = chosen();
    if (!c.length) { bulk.innerHTML = ""; return; }
    const tests = [...new Set(c.map((x) => NAME(x.dataset.test)))], runs = [...new Set(c.map((x) => x.dataset.run))];
    bulk.innerHTML = `<div class="card"><h3 style="margin-top:0">Raise an issue for ${c.length} gap${c.length === 1 ? "" : "s"}</h3>
      <div class="grid cols2"><div><label for="it">Title</label><input id="it" type="text" value="${esc(`${tests.length === 1 ? tests[0] : "Mixed tests"}: ${c.length} gap${c.length === 1 ? "" : "s"} in ${runs.join(", ")}`)}"></div>
        <div class="grid cols2"><div><label for="io">Owner</label><input id="io" type="text" placeholder="Who will fix it"></div><div><label for="id">Due</label><input id="id" type="date"></div></div></div>
      <label for="ix">What needs to happen</label><textarea id="ix" rows="2" placeholder="Optional"></textarea>
      <div class="row" style="margin-top:8px"><button class="primary" id="mk">Raise issue</button><span id="ie"></span></div></div>`;
    bulk.querySelector("#mk").onclick = async () => {
      const who = needName(); if (!who) return;
      try {
        const r = await post("/api/issues", { finding_ids: c.map((x) => +x.value), title: bulk.querySelector("#it").value, owner: bulk.querySelector("#io").value, due: bulk.querySelector("#id").value,
          description: bulk.querySelector("#ix").value, actor: who });
        navigate(`#/issues/${r.issue_id}`);
      } catch (e) { bulk.querySelector("#ie").innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
    };
  };
  app.querySelectorAll(".sel").forEach((x) => x.addEventListener("change", paint));
}
