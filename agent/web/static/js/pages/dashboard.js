import { app, state, api, post, esc, num, when, badge, help, navigate, needName, refresh } from "../core.js";
import { acceptanceCard, trapsCard } from "./acceptance.js";

const NAME = (k) => (state.config.check_types && state.config.check_types[k]) || k.replace(/_/g, " ");
const DOT = { critical: "var(--gap)", warning: "var(--unk)" };
const mins = (s) => (s == null ? "" : s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);
const tileSmall = (v, label) => `<div><div style="font-size:22px;font-weight:700">${esc(v)}</div><div class="small muted">${esc(label)}</div></div>`;

/* One row per item: a label, a bar scaled to the largest value, and the number. Every value is also written out, so the chart needs no hover. */
const hbars = (rows, color = "var(--info)") => {
  const max = Math.max(1, ...rows.map((r) => +r.value));
  return rows.map((r) => `<div class="hb"><div class="hb-l" title="${esc(r.label)}">${esc(r.label)}</div>
    <div class="hb-t"><span style="width:${(+r.value / max) * 100}%;background:${r.color || color}"></span></div><div class="hb-n">${num(r.value)}</div></div>`).join("");
};
const stacked = (rows) => rows.map((r) => {
  const e = +r.evidenced, g = +r.gaps, u = +r.cannot_determine, t = e + g + u || 1;
  return `<div class="hb"><div class="hb-l" title="${esc(r.label)}">${esc(r.label)}</div>
    <div class="hb-t stack" title="${num(e)} evidenced, ${num(g)} gap, ${num(u)} cannot determine"><span class="e" style="width:${(e / t) * 100}%"></span><span class="g" style="width:${(g / t) * 100}%"></span><span class="u" style="width:${(u / t) * 100}%"></span></div>
    <div class="hb-n"><span style="color:var(--gap);font-weight:700">${num(g)}</span> <span class="muted">gaps</span></div></div>`;
}).join("");

/* What an auditor's sample would contain: expected accounts with a gap, with the range the sample size makes likely. */
function forecastCard(d) {
  const f = d.forecast, r = d.readiness || {};
  const running = r.status === "running";
  const button = `<button class="${f ? "" : "primary"}" id="ready" ${running ? "disabled" : ""}>${running ? "Readiness check running…" : f ? "Run again" : "Run a readiness check"}</button>`;
  const body = f ? `<p class="small muted" style="margin-top:0">If an auditor samples ${num(f.sample)} accounts, this is how many we expect to have a gap, from a random check of ${num(r.accounts || 0)} accounts
      (<a href="#/run/${f.run_id}">${esc(f.request_id)}</a>, ${when(f.finished_at)}). The range is a 95% interval.</p>
      <table><thead><tr><th>Test</th><th class="num">Expected</th><th>Range</th></tr></thead><tbody>${f.tests.map((t) => {
        const w = (x) => (x / f.sample) * 100;
        return `<tr><td>${esc(NAME(t.check_type))}</td><td class="num"><strong>${num(t.expected)}</strong></td><td style="min-width:150px"><div class="range" title="${t.low} to ${t.high}"><span style="left:${w(t.low)}%;width:${Math.max(1, w(t.high - t.low))}%"></span><i style="left:${w(t.expected)}%"></i></div><div class="small muted">${t.low} to ${t.high}</div></td></tr>`;
      }).join("")}</tbody></table>`
    : `<p class="muted">No readiness check yet. It runs the same audit on a random sample before anyone asks, so you know what an auditor will find. ${running ? "One is running now." : "About 20 minutes for 1,000 accounts."}</p>`;
  return `<div class="card"><div class="row between"><h2 style="margin:0">Before the auditor arrives</h2>${button}</div>${body}</div>`;
}

export async function dashboardPage() {
  const d = await api("/api/dashboard");
  const { runs, totals: t, severity, by_check: byCheck, months, agencies, agent, recent, attention, traps } = d;
  const maxM = Math.max(1, ...months.map((m) => +m.gaps));
  const sevColor = (i) => ["var(--gap)", "#c2570c", "var(--info)"][Math.min(i, 2)];
  const latest = d.latest_run;
  app.innerHTML = `
    <div class="row between"><div><h1>Dashboard ${help("audit")}</h1>
      <p class="muted" style="max-width:70ch">Answer any audit request with a complete evidence pack within a day, and report every gap before the auditor finds it.</p></div>
      <a class="btn primary big" href="#/new">New audit request</a></div>
    ${runs.total ? "" : `<div class="card"><div class="empty"><p>No audits yet. Start with a request from a lender or regulator.</p><a class="btn primary" href="#/new">Start your first audit request</a></div></div>`}
    <div class="grid cols3 beats">
      <div class="beat"><div class="k">Any request</div><div class="n">${num(runs.completed)}</div><div class="l">audits answered, each worded differently; every question becomes a test, an agency document to request, or a plain "cannot determine"</div></div>
      <div class="beat"><div class="k">Within a day</div><div class="n">${latest ? mins(latest.seconds) : "—"}</div><div class="l">${latest ? `to test ${num(latest.accounts)} accounts on ${num(latest.checks)} tests in ${esc(latest.request_id)} (the limit is 2 hours)` : "for the latest audit"}</div></div>
      <div class="beat"><div class="k">Before the auditor</div><div class="n">${num(t.gaps)}</div><div class="l">gaps reported with their evidence, ${num(t.gaps_reviewed)} reviewed; ${d.forecast ? "a readiness check forecasts what any sample would hold" : "run a readiness check to forecast what any sample would hold"}</div></div>
    </div>
    <div class="grid cols2" style="margin-top:14px;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);align-items:start">
      ${acceptanceCard(d.acceptance, d.latest_run ? d.latest_run.run_id : "", d.latest_run ? `Acceptance criteria: ${d.latest_run.request_id}` : "Acceptance criteria")}
      <div class="card"><h2 style="margin-top:0">Needs attention</h2>
        ${attention.length ? `<ul class="attn">${attention.map((a) => `<li><span class="dot" style="background:${DOT[a.level]}" title="${a.level}"></span>
          <div><a href="${a.link}"><strong>${esc(a.run)}</strong></a>: ${esc(a.text)}</div></li>`).join("")}</ul>` : `<div class="empty">Nothing needs attention.</div>`}</div>
    </div>
    <div class="grid cols2" style="margin-top:14px;align-items:start">
      ${trapsCard(traps)}
      ${forecastCard(d)}
    </div>
    <div class="grid cols2" style="margin-top:14px;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);align-items:start">
      <div class="card"><h2 style="margin-top:0">Results by test</h2>
        <div class="legend"><span><i class="e"></i>evidenced</span><span><i class="g"></i>gap</span><span><i class="u"></i>cannot determine</span></div>
        ${byCheck.length ? stacked(byCheck.map((r) => ({ ...r, label: NAME(r.check_type) }))) : `<div class="empty">No results yet.</div>`}</div>
      <div class="card"><h2 style="margin-top:0">Gaps by severity</h2>
        ${severity.length ? hbars(severity.map((s, i) => ({ label: s.severity, value: s.n, color: sevColor(i) }))) : `<div class="empty">No gaps.</div>`}
        <div class="grid cols2" style="margin-top:14px">
          ${tileSmall(`${t.skeptic_flagged}`, `of ${num(t.skeptic_read)} gaps read a second time are disputed or unsure`)}
          ${tileSmall(`${agent.found_elsewhere}`, "cases of missing evidence found by the agent in another system")}
        </div></div>
    </div>
    <div class="grid cols2" style="margin-top:14px;align-items:start">
      <div class="card"><h2 style="margin-top:0">Gaps by agency</h2>
        ${agencies.length ? hbars(agencies.map((a) => ({ label: a.agency, value: a.gaps }))) : `<div class="empty">No call-level gaps.</div>`}
        <p class="small muted" style="margin-bottom:0">Calls with a gap, by the collector's agency.</p></div>
      <div class="card"><h2 style="margin-top:0">When the gaps occurred</h2>
        ${months.length ? `<div class="cols">${months.map((m) => `<div style="height:${(m.gaps / maxM) * 100}%" title="${esc(m.month)}: ${num(m.gaps)} gaps"></div>`).join("")}</div>
          <div class="cols-l">${months.map((m) => `<span>${esc(m.month.slice(5))}</span>`).join("")}</div>
          <p class="small muted" style="margin-bottom:0">Gap findings on calls and messages by month; the busiest month has ${num(maxM)}.</p>` : `<div class="empty">No dated gaps.</div>`}</div>
    </div>
    <div class="card" style="margin-top:14px"><div class="row between"><h2 style="margin:0">Recent audits</h2><a href="#/audits">All audit requests</a></div>
      <table style="margin-top:10px"><thead><tr><th>Request</th><th>Status</th><th class="num">Accounts</th><th class="num">Tests</th><th class="num">Gaps</th><th>Testing time <span class="muted small">(limit: 2 hours)</span></th><th>Letter</th></tr></thead><tbody>
      ${recent.map((r) => `<tr class="click" data-run="${r.run_id}"><td><strong>${esc(r.request_id)}</strong><div class="small muted">${esc(r.lender || "")} ${when(r.started_at)}</div></td><td>${badge(r.status)}</td>
        <td class="num">${num(r.accounts)}</td><td class="num">${num(r.checks)}</td><td class="num"><strong style="color:${+r.gaps ? "var(--gap)" : "inherit"}">${num(r.gaps)}</strong></td>
        <td style="min-width:170px">${r.seconds == null ? "" : `<div class="hb-t slim" title="${mins(r.seconds)} of ${mins(d.sla_seconds)}"><span style="width:${Math.max(2, Math.min(100, (r.seconds / d.sla_seconds) * 100))}%;background:var(--ok)"></span></div><div class="small muted">${mins(r.seconds)}</div>`}</td>
        <td>${r.letter_status ? `<span class="badge b-${r.letter_status}">${esc(r.letter_status.replace("_", " "))}</span>` : `<span class="muted small">not started</span>`}</td></tr>`).join("")}
      </tbody></table></div>`;
  app.querySelectorAll("tr[data-run]").forEach((tr) => tr.addEventListener("click", () => navigate(`#/run/${tr.dataset.run}`)));
  const ready = document.getElementById("ready");
  if (ready) ready.onclick = async () => {
    const who = needName(); if (!who) return;
    ready.disabled = true; ready.textContent = "Starting…";
    try { const r = await post("/api/readiness", { requested_by: who, size: 1000 }); navigate(`#/run/${r.run_id}`); }
    catch (e) { ready.disabled = false; ready.textContent = "Run a readiness check"; alert(e.message); }
  };
  if (d.readiness && d.readiness.status === "running") state.poll = setInterval(refresh, 20000);
}
