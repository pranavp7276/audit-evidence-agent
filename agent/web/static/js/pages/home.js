import { app, api, esc, num, when, fdate, help, badge, stackBar, navigate } from "../core.js";

export async function homePage() {
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
  app.querySelectorAll("tr[data-run]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/run/${tr.dataset.run}`)));
  const hh = document.getElementById("hide-hint");
  if (hh) hh.onclick = () => { try { localStorage.setItem("seenGuide", "1"); } catch (_) {} hh.closest(".note").remove(); };
}
