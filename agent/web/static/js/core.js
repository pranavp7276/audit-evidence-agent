export const app = document.getElementById("app");
export const state = { poll: null, config: {}, rules: null, seq: 0 };

/* ---------- formatting ---------- */
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const num = (n) => Number(n || 0).toLocaleString();
export const when = (s) => (s ? new Date(s).toLocaleString() : "");
export const fdate = (s) => (s ? new Date(String(s).slice(0, 10) + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "");
export const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);
export const duration = (a, b) => {
  if (!a || !b) return "";
  const s = Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000));
  return s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min` : s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
};
export const STATUS_LABEL = { evidenced: "Evidenced", gap: "Gap", cannot_determine: "Cannot determine" };

/* ---------- api ---------- */
export async function api(path, opts) {
  const gen = state.seq, isGet = !opts || !opts.method || opts.method === "GET";
  const r = await fetch(path, opts);
  if (isGet && gen !== state.seq) throw Object.assign(new Error("superseded"), { stale: true }); // the user already navigated elsewhere
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
    throw new Error(msg);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r;
}
export const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

/* ---------- reviewer name ---------- */
export const reviewer = () => { try { return localStorage.getItem("reviewer") || ""; } catch (_) { return ""; } };
export function setReviewer(v) { try { localStorage.setItem("reviewer", v); } catch (_) {} renderWho(); }
export function renderWho() { document.getElementById("who").textContent = reviewer() ? `Signed in as ${reviewer()}` : "Set your name"; }
export function needName() {
  if (reviewer()) return reviewer();
  const n = (window.prompt("Your name (recorded on every review and letter change):") || "").trim();
  if (n) setReviewer(n);
  return n;
}

/* ---------- rendering helpers ---------- */
export const badge = (status) => `<span class="badge b-${esc(status)}">${esc(STATUS_LABEL[status] || String(status).replace(/_/g, " "))}</span>`;
export function sevBadge(label, scale) {
  if (!label) return "";
  const i = Math.min(Math.max(scale.indexOf(label), 0), 3);
  return `<span class="badge sev sev-${i}">${esc(label)}</span>`;
}
export function stackBar(e, g, u) {
  const t = (e + g + u) || 1;
  return `<div class="bar" title="${e} evidenced, ${g} gap, ${u} cannot determine"><span class="e" style="width:${(e / t) * 100}%"></span><span class="g" style="width:${(g / t) * 100}%"></span><span class="u" style="width:${(u / t) * 100}%"></span></div>`;
}
export const stat = (n, label, cls = "") => `<div class="stat ${cls}"><div class="n">${num(n)}</div><div class="l">${esc(label)}</div></div>`;
export const help = (topic) => `<a class="help no-print" href="#/guide/${topic}">Help</a>`;
export const info = (type) => (state.rules && state.rules.checks[type]) || { title: type, tests: "", sources: [] };

function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])_([^_]+)_(?=[\s).,;]|$)/g, "$1<em>$2</em>").replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1");
}
export function markdown(md) {
  const out = []; let list = false, table = [];
  const flush = () => {
    if (!table.length) return;
    const rows = table.filter((r) => !/^\|\s*-/.test(r)).map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
    out.push("<table><thead><tr>" + rows[0].map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>" +
      rows.slice(1).map((r) => "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</tbody></table>");
    table = [];
  };
  for (const line of md.split("\n")) {
    if (line.startsWith("|")) { table.push(line); continue; }
    flush();
    if (/^- /.test(line)) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(line.slice(2))}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    const h = line.match(/^(#{1,3}) (.*)/);
    if (h) out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  flush(); if (list) out.push("</ul>");
  return out.join("\n");
}
export function download(name, text, type = "text/plain") {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click();
}

/* Pages never import the router: they ask for navigation through these two. */
export const navigate = (hash) => { location.hash = hash; };
export const refresh = () => window.dispatchEvent(new Event("app:refresh"));

/* A row of links for the pages inside one area; items are [href, label, count?]. */
export const subnav = (items, activeHref, label = "") =>
  `<nav class="subnav no-print" aria-label="${esc(label)}">${label ? `<span class="subnav-label">${esc(label)}</span>` : ""}${items.map(([href, text, n]) => `<a href="${href}" class="${href === activeHref ? "active" : ""}">${esc(text)}${n ? ` <span class="tag">${num(n)}</span>` : ""}</a>`).join("")}</nav>`;

/* The three pages that together say what an audit is tested against. */
export const rulebookNav = (active) => subnav([["#/kb", "1. Knowledge base"], ["#/guardrails", "2. Guardrails"], ["#/rules", "3. Rules & data"]], active, "Rulebook");
