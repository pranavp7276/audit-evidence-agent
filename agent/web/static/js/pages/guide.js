import { app, state, post, esc } from "../core.js";
import { GUIDE } from "../guide-content.js";

async function askAssistant(topicText) {
  const q = document.getElementById("ask-q").value.trim(), out = document.getElementById("ask-a");
  if (!q) return;
  out.innerHTML = `<span class="muted">Thinking…</span>`;
  try {
    const r = await post("/api/assist", { question: q, context: topicText });
    out.innerHTML = `<div class="card" style="margin:8px 0 0"><div style="white-space:pre-wrap">${esc(r.answer)}</div><div class="small muted" style="margin-top:6px">Answered from this guide page by ${esc(r.model)}. Check the guide itself if it matters.</div></div>`;
  } catch (e) { out.innerHTML = `<div class="note">${esc(e.message)}</div>`; }
}

export function guidePage(topic) {
  const t = GUIDE.find((x) => x.id === topic) || GUIDE[0];
  try { localStorage.setItem("seenGuide", "1"); } catch (_) {}
  app.innerHTML = `<div class="guide"><nav class="toc no-print">${GUIDE.map((x) => `<a href="#/guide/${x.id}" class="${x.id === t.id ? "active" : ""}">${esc(x.title)}</a>`).join("")}</nav>
    <div class="doc">${t.html}
      ${state.config.parser === "llm" ? `<div class="no-print" style="margin-top:20px;padding:12px;border:1px solid var(--border);border-radius:4px;background:var(--surface2)"><label for="ask-q">Ask a question about this page</label>
        <div class="row"><input id="ask-q" type="text" style="flex:1;min-width:240px" placeholder="e.g. Why can't I approve the letter?"><button id="ask-go" class="primary">Ask</button></div><div id="ask-a"></div></div>` : ""}
      <div class="row between no-print" style="margin-top:22px;padding-top:12px;border-top:1px solid var(--border)">
        ${GUIDE.indexOf(t) > 0 ? `<a href="#/guide/${GUIDE[GUIDE.indexOf(t) - 1].id}">&larr; ${esc(GUIDE[GUIDE.indexOf(t) - 1].title)}</a>` : "<span></span>"}
        ${GUIDE.indexOf(t) < GUIDE.length - 1 ? `<a href="#/guide/${GUIDE[GUIDE.indexOf(t) + 1].id}">${esc(GUIDE[GUIDE.indexOf(t) + 1].title)} &rarr;</a>` : "<span></span>"}</div></div></div>`;
  const go = document.getElementById("ask-go");
  if (go) {
    const plain = new DOMParser().parseFromString(t.html, "text/html").body.textContent.replace(/\s+/g, " ");
    go.onclick = () => askAssistant(plain);
    document.getElementById("ask-q").addEventListener("keydown", (e) => { if (e.key === "Enter") askAssistant(plain); });
  }
}
