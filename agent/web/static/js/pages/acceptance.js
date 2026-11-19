import { esc, num } from "../core.js";

/* The acceptance criteria from the problem statement, shown as a scorecard: what was measured, against which target, and whether it passes.
   Recall and false gaps need an answer key, which a real (hidden) request does not come with, so they say so instead of showing a number. */

const pct1 = (x) => `${(x * 100).toFixed(1)}%`;
const mins = (s) => (s == null ? "" : s < 90 ? `${s} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`);

function row(state, name, target, value, detail) {
  const chip = state === "pass" ? `<span class="badge b-completed">Pass</span>` : state === "fail" ? `<span class="badge b-failed">Fail</span>` : `<span class="badge b-draft">Needs key</span>`;
  return `<tr><td style="width:84px">${chip}</td><td><strong>${esc(name)}</strong><div class="small muted">${esc(target)}</div></td><td class="num" style="white-space:nowrap"><strong>${value}</strong></td><td class="small muted">${detail}</td></tr>`;
}

export function acceptanceCard(a, runId, title = "Acceptance criteria") {
  if (!a) return `<div class="card"><h2 style="margin-top:0">${esc(title)}</h2><div class="empty">Shown once an audit has completed.</div></div>`;
  const s = a.score, c = a.citations;
  const rows = [
    s ? row(s.recall >= a.targets.recall ? "pass" : "fail", "Gap recall", "at least 95% of the true gaps reported", pct1(s.recall), `${num(s.matched)} of ${num(s.true_gaps)} true gaps (answer key ${esc(s.key)})`)
      : row("key", "Gap recall", "at least 95% of the true gaps reported", "—", `Needs the true gaps for this request. <a href="#/run/${runId}/pack">Score against a key</a>`),
    s ? row(s.false_gap_rate < a.targets.false_gap_rate ? "pass" : "fail", "False gaps", "under 5% of reported gaps", pct1(s.false_gap_rate), `${num(s.false_gaps)} of ${num(s.reported_gaps)} reported gaps`)
      : row("key", "False gaps", "under 5% of reported gaps", "—", "Needs the same answer key."),
    row(a.unsupported === 0 ? "pass" : "fail", "Claims without a cited record", "zero", num(a.unsupported), "An evidenced or gap finding with no citation is rejected by the database as well."),
    c ? row(c.verified === c.checked ? "pass" : "fail", "Every cited record exists", "each citation re-read from its source table", `${num(c.verified)} / ${num(c.checked)}`, "Looked up again through the warehouse SQL tool after the findings were saved.")
      : row("key", "Every cited record exists", "each citation re-read from its source table", "—", "Not yet checked for this audit."),
    a.seconds == null ? "" : row(a.seconds < a.sla_seconds ? "pass" : "fail", "Time to complete", "under 2 hours", mins(a.seconds), "From the start of testing to the saved pack."),
  ].join("");
  return `<div class="card"><h2 style="margin-top:0">${esc(title)}</h2><table><tbody>${rows}</tbody></table></div>`;
}

/* The subtle traps in the evidence that the audit caught: each says why a hurried read would miss it, and opens an example. */
export function trapsCard(traps, title = "Subtle traps in the evidence, caught") {
  if (!traps || !traps.length) return `<div class="card"><h2 style="margin-top:0">${esc(title)}</h2><div class="empty">None found.</div></div>`;
  const max = Math.max(...traps.map((t) => +t.count));
  return `<div class="card"><h2 style="margin-top:0">${esc(title)}</h2>
    <p class="small muted" style="margin-top:0">Cases where a quick read says compliant and the records say otherwise, or where the platform refuses to say compliant at all.</p>
    ${traps.map((t) => {
      const page = t.status === "gap" ? "gaps" : "followup", link = `#/run/${t.example_run}/${page}?${new URLSearchParams({ text: t.text })}`;
      return `<div class="trap"><div class="row between"><a href="${link}"><strong>${esc(t.label)}</strong></a><span class="num"><strong>${num(t.count)}</strong></span></div>
        <div class="hb-t slim"><span style="width:${(+t.count / max) * 100}%;background:${t.status === "gap" ? "var(--gap)" : "#d9a400"}"></span></div>
        <div class="small muted">${esc(t.why)}${t.face_value_misses != null ? ` <strong style="color:var(--text)">${num(t.face_value_misses)} of these would have passed if the logged clock had been taken at face value.</strong>` : ""}</div></div>`;
    }).join("")}</div>`;
}
