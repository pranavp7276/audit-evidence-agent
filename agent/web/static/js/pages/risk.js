import { app, state, api, esc, num, help } from "../core.js";

/* Risk assessment: how likely each test is to find a gap, and how serious a gap on it is. Likelihood is measured from the audits; impact is the
   severity the request's own scale gives that kind of gap. */

const NAME = (k) => (state.config.check_types && state.config.check_types[k]) || k.replace(/_/g, " ");
const RATING = { High: "var(--gap)", Medium: "#d9a400", Low: "var(--ok)" };
const TINT = { High: "var(--gap-bg)", Medium: "var(--unk-bg)", Low: "var(--ok-bg)" };
const BANDS = ["Low", "Medium", "High"];
const rate = (l, i) => ((l + 1) * (i + 1) >= 6 ? "High" : (l + 1) * (i + 1) >= 3 ? "Medium" : "Low");

export async function riskPage() {
  const d = await api("/api/risk");
  const cell = (l, i) => {
    const here = d.tests.filter((t) => t.likelihood_band === BANDS[l] && t.impact_band === BANDS[i]);
    return `<div class="rcell" style="background:${TINT[rate(l, i)]}">${here.map((t) => `<span class="rpill" style="border-color:${RATING[t.rating]}" title="${esc(NAME(t.check_type))}: ${Math.round(t.likelihood * 100)}% of accounts, impact ${t.impact}">${esc(NAME(t.check_type))}</span>`).join("")}</div>`;
  };
  const maxPts = Math.max(1, ...d.agencies.map((a) => +a.points));
  app.innerHTML = `
    <h1>Risk ${help("audit")}</h1>
    <p class="muted" style="max-width:72ch">Where to look first. Likelihood is the share of tested accounts that had a gap, over every completed audit. Impact is how serious a gap on that test is, from the severity the request's scale gives it. Both are placed in a band, and the bands combine into a rating.</p>
    <div class="grid cols2" style="align-items:start;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr)">
      <div class="card"><h2 style="margin-top:0">Risk matrix</h2>
        ${d.tests.length ? `<div class="matrix"><div class="ax y">Impact</div><div class="mgrid">
          ${[2, 1, 0].map((i) => `<div class="ml">${BANDS[i]}</div>${[0, 1, 2].map((l) => cell(l, i)).join("")}`).join("")}
          <div></div>${BANDS.map((b) => `<div class="ml c">${b}</div>`).join("")}</div><div class="ax x">Likelihood of a gap</div></div>` : `<div class="empty">Complete an audit to see the matrix.</div>`}</div>
      <div class="card"><h2 style="margin-top:0">Gap points by agency</h2><p class="small muted" style="margin-top:0">Each gap on a call counts for its severity (first on the scale 5, second 3, later 1).</p>
        ${d.agencies.length ? d.agencies.map((a) => `<div class="hb"><div class="hb-l" title="${esc(a.agency)}">${esc(a.agency)}</div><div class="hb-t"><span style="width:${(a.points / maxPts) * 100}%;background:var(--gap)"></span></div><div class="hb-n">${num(a.points)}</div></div>`).join("") : `<div class="empty">No call-level gaps.</div>`}</div>
    </div>
    <div class="card" style="margin-top:14px"><h2 style="margin-top:0">By test</h2><table><thead><tr><th>Test</th><th>Likelihood</th><th class="num">Impact</th><th>Rating</th><th class="num">Score</th></tr></thead><tbody>
      ${d.tests.map((t) => `<tr><td><strong>${esc(NAME(t.check_type))}</strong>${t.priority_weight > 1 ? ` <span class="tag" title="Review priority weight from the guardrail">priority ${t.priority_weight}</span>` : ""}</td>
        <td style="min-width:200px"><div class="hb-t slim"><span style="width:${Math.max(2, t.likelihood * 100)}%;background:${RATING[t.rating]}"></span></div><div class="small muted">${Math.round(t.likelihood * 100)}% · ${num(t.with_gap)} of ${num(t.tested)} accounts (${t.likelihood_band.toLowerCase()})</div></td>
        <td class="num">${t.impact} <span class="muted small">(${t.impact_band.toLowerCase()})</span></td><td><span class="badge" style="color:${RATING[t.rating]};border-color:${RATING[t.rating]};background:${TINT[t.rating]}">${t.rating}</span></td><td class="num">${t.score}</td></tr>`).join("")
        || `<tr><td colspan="5"><div class="empty">No audits completed yet.</div></td></tr>`}</tbody></table>
      <p class="small muted" style="margin-bottom:0">Likelihood bands: under 10% low, 10% to 30% medium, 30% or more high. Impact: 5 high, 3 medium, 1 low. The rating is the product of the two band numbers: 6 or more high, 3 to 4 medium, otherwise low. The score is likelihood × impact.</p></div>`;
}
