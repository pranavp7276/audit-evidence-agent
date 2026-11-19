import { esc } from "../core.js";
import { showRecord } from "./findings.js";

/* The evidence map of one account: every call, message, consent, recording and notice on a time axis (India time).
   Calls and messages sit at their hour of the day, with the permitted window shaded, so a call outside it is visible at a glance.
   For each gap, a red line joins the records it cites, so "message sent / consent withdrawn" reads as one picture. */

const W = 960, LEFT = 96, RIGHT = 18, TOP = 8;
const LANES = [
  { key: "call", label: "Calls", h: 124, hours: true, kinds: ["call"] },
  { key: "msg", label: "Messages", h: 74, hours: true, kinds: ["whatsapp", "sms"] },
  { key: "consent", label: "Consent", h: 30, kinds: ["consent"] },
  { key: "recording", label: "Recordings", h: 30, kinds: ["recording"] },
  { key: "notice", label: "Notices", h: 30, kinds: ["notice"] },
];
const IST_MIN = 330;
const ist = (iso, allDay) => { const t = new Date(allDay ? `${String(iso).slice(0, 10)}T06:30:00Z` : iso).getTime(); return t + IST_MIN * 60000; };
const hourOf = (ms) => { const d = new Date(ms); return d.getUTCHours() + d.getUTCMinutes() / 60; };
const SOURCE_TABLE = { call: "cn_core.tele_process_instance_call_logs", whatsapp: "cn_core.communication_dashboard_t", sms: "cn_core.communication_dashboard_t",
  consent: "compliance.customer_consent", recording: "compliance.call_recording", notice: "compliance.notice" };

function shape(kind, x, y, flagged) {
  const r = flagged ? 6.5 : 4.5, cls = `mk k-${kind}`;
  if (kind === "consent") return `<path class="${cls}" d="M${x} ${y - r - 1}L${x + r + 1} ${y}L${x} ${y + r + 1}L${x - r - 1} ${y}Z"/>`;
  if (kind === "recording") return `<rect class="${cls}" x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" rx="1.5"/>`;
  if (kind === "notice") return `<path class="${cls}" d="M${x} ${y - r - 1}L${x + r + 1} ${y + r}L${x - r - 1} ${y + r}Z"/>`;
  return `<circle class="${cls}" cx="${x}" cy="${y}" r="${r}"/>`;
}

export function evidenceMap(events, findings) {
  if (!events.length) return "";
  const times = events.map((e) => ist(e.ts, e.all_day));
  let lo = Math.min(...times), hi = Math.max(...times);
  const pad = Math.max((hi - lo) * 0.03, 86400000); lo -= pad; hi += pad;
  const x = (ms) => LEFT + ((ms - lo) / (hi - lo)) * (W - LEFT - RIGHT);
  let top = TOP;
  const lanes = LANES.map((l) => { const o = { ...l, y: top }; top += l.h + 8; return o; });
  const H = top + 22;
  const laneOf = (kind) => lanes.find((l) => l.kinds.includes(kind));
  const yIn = (l, ms) => (l.hours ? l.y + 8 + (hourOf(ms) / 24) * (l.h - 16) : l.y + l.h / 2);
  const pos = {}; // record id -> {x, y}
  const marks = events.map((e, i) => {
    const l = laneOf(e.kind); if (!l) return "";
    const ms = times[i], px = x(ms), py = yIn(l, ms);
    pos[e.id] = { x: px, y: py };
    const tip = `${e.title}\n${e.all_day ? "date only" : new Date(ms).toISOString().replace("T", " ").slice(0, 16) + " IST"}\n${e.detail}`;
    return `<g class="ev-mk ${e.flag ? "flag-" + e.flag : ""}" data-rec="${esc(e.id)}" data-table="${SOURCE_TABLE[e.kind] || ""}" tabindex="0" role="button" aria-label="${esc(e.title)}"><title>${esc(tip)}</title>${shape(e.kind, +px.toFixed(1), +py.toFixed(1), !!e.flag)}</g>`;
  }).join("");
  // axis: a tick at the start of each month in the range
  const ticks = []; const d0 = new Date(lo); let m = new Date(Date.UTC(d0.getUTCFullYear(), d0.getUTCMonth() + 1, 1));
  while (+m < hi) { ticks.push(+m); m = new Date(Date.UTC(m.getUTCFullYear(), m.getUTCMonth() + 1, 1)); }
  const stepEvery = Math.max(1, Math.ceil(ticks.length / 12));
  const axis = ticks.map((t, i) => `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${TOP}" y2="${top - 8}"/>${i % stepEvery === 0 ? `<text class="axl" x="${x(t)}" y="${H - 6}" text-anchor="middle">${new Date(t).toLocaleString(undefined, { month: "short", year: "2-digit", timeZone: "UTC" })}</text>` : ""}`).join("");
  const bands = lanes.map((l) => {
    const win = l.hours ? `<rect class="win" x="${LEFT}" y="${l.y + 8 + (8 / 24) * (l.h - 16)}" width="${W - LEFT - RIGHT}" height="${(11 / 24) * (l.h - 16)}"/>
      <text class="axl" x="${LEFT - 8}" y="${l.y + 8 + (8 / 24) * (l.h - 16) + 4}" text-anchor="end">08:00</text><text class="axl" x="${LEFT - 8}" y="${l.y + 8 + (19 / 24) * (l.h - 16) + 4}" text-anchor="end">19:00</text>` : "";
    return `<rect class="lane" x="0" y="${l.y}" width="${W}" height="${l.h}"/>${win}<text class="lane-l" x="8" y="${l.y + (l.hours ? 16 : l.h / 2 + 4)}">${l.label}</text>`;
  }).join("");
  // one red (or amber) line per gap or undetermined finding, through the records it cites
  const links = findings.filter((f) => f.status !== "evidenced").slice(0, 40).map((f) => {
    const ids = [...new Set([f.subject_ref, ...f.citations.map((c) => c.record_key)].filter((k) => k && pos[k]))];
    const pts = ids.map((k) => pos[k]).sort((a, b) => a.x - b.x);
    return pts.length > 1 ? `<polyline class="link ${f.status === "gap" ? "gap" : "unk"}" points="${pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}"><title>${esc(f.check_id)}: ${esc(f.reason)}</title></polyline>` : "";
  }).join("");
  const legend = [["call", "Call"], ["whatsapp", "Message"], ["consent", "Consent"], ["recording", "Recording"], ["notice", "Notice"]]
    .map(([k, t]) => `<span class="lg"><svg width="16" height="14" viewBox="0 0 16 14" aria-hidden="true">${shape(k, 8, 7, false)}</svg>${t}</span>`).join("");
  return `<div class="card emap"><div class="row between"><h3 style="margin:0">Evidence map <span class="small muted">(India time)</span></h3>
      <div class="legend">${legend}<span class="lg"><i class="g"></i>gap</span><span class="lg"><i class="u"></i>cannot determine</span></div></div>
    <div class="scroll"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Timeline of every call, message, consent, recording and notice for this account. Calls and messages are placed by hour of day with the permitted calling window shaded. Lines join the records each gap cites.">
      ${bands}${axis}${links}${marks}</svg></div>
    <p class="small muted" style="margin:6px 0 0">Calls and messages sit at their hour of the day; the shaded band is 08:00 to 19:00. Red outlines and lines mark gaps, amber marks what could not be determined. Click any mark to see the source record.</p></div>`;
}

export function wireEvidenceMap(root) {
  const open = (g) => g.dataset.table && showRecord(g.dataset.table, g.dataset.rec);
  root.querySelectorAll(".ev-mk").forEach((g) => {
    g.addEventListener("click", () => open(g));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(g); } });
  });
}
