import { app, state, api, reviewer, setReviewer, renderWho } from "./core.js";
import { registerPage, route } from "./router.js";
import { homePage } from "./pages/home.js";
import { reportsPage } from "./pages/reports.js";
import { newRequestPage } from "./pages/newrequest.js";
import { workspace } from "./pages/workspace.js";
import { rulesPage } from "./pages/rules.js";
import { kbPage, kbDocPage } from "./pages/kb.js";
import { guardrailsPage } from "./pages/guardrails.js";
import { guidePage } from "./pages/guide.js";
import { sqlPage } from "./pages/explorer.js";

registerPage("", homePage);
registerPage("audits", homePage);
registerPage("new", newRequestPage);
registerPage("reports", reportsPage);
registerPage("rules", () => rulesPage(app, true));
registerPage("guide", ({ parts }) => guidePage(parts[1] || "start"));
registerPage("kb", ({ parts }) => (parts[1] ? kbDocPage(parts[1]) : kbPage()));
registerPage("guardrails", ({ q }) => guardrailsPage(q));
registerPage("sql", sqlPage);
registerPage("run", ({ parts, q }) => (parts[1] ? workspace(parts[1], parts[2] || "summary", parts[3], q) : homePage()));

document.getElementById("who").addEventListener("click", () => {
  const n = (window.prompt("Your name:", reviewer()) || "").trim();
  if (n) setReviewer(n);
});
renderWho();
try {
  [state.config, state.rules] = await Promise.all([api("/api/config"), api("/api/rules")]);
  document.getElementById("parser-badge").textContent = state.config.parser === "llm" ? `Models on: ${state.config.models.decision}, ${state.config.models.reasoning}` : "Models off: keyword reader in use";
} catch (_) {}
route();
