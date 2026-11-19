import { app, api, esc } from "../core.js";

/* Alerts: what needs a person, most urgent first. The same items feed the count beside Alerts in the menu. */

const DOT = { critical: "var(--gap)", warning: "var(--unk)" };
const KIND = { audit: "Audit", issue: "Issue", plan: "Plan" };

export async function alertsPage() {
  const a = await api("/api/alerts");
  paintCount(a);
  app.innerHTML = `
    <h1>Alerts</h1>
    <p class="muted">Overdue responses, gaps nobody has reviewed, failed audits, issues and planned audits that are due. ${a.count ? `${a.critical} urgent, ${a.count - a.critical} to watch.` : ""}</p>
    <div class="card">${a.items.length ? `<ul class="attn">${a.items.map((x) => `<li><span class="dot" style="background:${DOT[x.level]}" title="${x.level}"></span>
      <div><span class="tag">${KIND[x.kind] || ""}</span> <a href="${x.link}"><strong>${esc(x.run)}</strong></a>: ${esc(x.text)}</div></li>`).join("")}</ul>` : `<div class="empty">Nothing needs attention.</div>`}</div>`;
}

export function paintCount(a) {
  const el = document.getElementById("alert-count");
  if (el) { el.textContent = a.count ? String(a.count) : ""; el.hidden = !a.count; el.classList.toggle("urgent", a.critical > 0); }
}
