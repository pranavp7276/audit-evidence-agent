import { app, state, esc } from "./core.js";

const pages = {}; // first path segment -> render function; "" is the default page
export const registerPage = (key, render) => { pages[key] = render; };

function stopPolling() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
function parseHash() {
  const [path, query = ""] = location.hash.slice(1).split("?");
  return { parts: path.split("/").filter(Boolean), q: Object.fromEntries(new URLSearchParams(query)) };
}
export async function route() {
  state.seq++;
  stopPolling();
  const { parts, q } = parseHash();
  const section = { new: "new", rules: "rules", kb: "kb", guardrails: "guardrails", guide: "guide" }[parts[0]] || "runs";
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === section));
  try {
    await (pages[parts[0]] || pages[""])({ parts, q });
  } catch (e) {
    if (e.stale) return;
    app.innerHTML = `<div class="err">${esc(e.message)}</div><p><a href="#/">Back to audit requests</a></p>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
window.addEventListener("app:refresh", route);
