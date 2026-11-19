import { api, esc, markdown } from "../core.js";

export async function packTab(el, d, runId) {
  const { markdown: md } = await api(`/api/runs/${runId}/index`);
  const files = [["gap_report.csv", "Gap report: every gap graded by severity, with the records cited and the review decision"], ["follow_up.csv", "Items that could not be determined, to chase"],
    ["reviews.csv", "Review trail: who decided what, and when"], ["response_letter.md", "The response letter (latest saved version)"], ["rules_and_assumptions.md", "What each check tests and the interpretations applied"], ["index.md", "Index of the pack"]];
  const keys = await api("/api/gap-keys");
  el.innerHTML = `<div class="card"><div class="row between"><div><h2 style="margin:0">Evidence pack</h2><p class="muted small" style="margin:4px 0 0">Everything an auditor needs to trace each statement to a record. The pack is rebuilt from the current state every time you download it.</p></div>
    <a class="btn primary big" href="/api/runs/${runId}/pack.zip">Download full pack (.zip)</a></div>
    <h3>Contents</h3><ul>${files.map(([n, t]) => `<li><a href="/api/runs/${runId}/files/${n}">${n}</a> <span class="muted small">— ${esc(t)}</span></li>`).join("")}<li><strong>extracts/&lt;check&gt;.csv</strong> <span class="muted small">— one row per finding with its citations and extracts, per check (in the zip)</span></li></ul></div>
    <div class="card"><h2>Index</h2><div class="md">${markdown(md)}</div></div>
    <details class="card no-print"><summary style="margin:0">Quality check: score this audit against a known gap key</summary>
      <p class="muted small">If you hold the true gap list for this request, compare it to what the platform reported (target: recall ≥ 95%, false gaps &lt; 5%, no claims without a citation).</p>
      <form id="sf" class="row">${keys.length ? `<div><label>Gap key on this server</label><select name="key_name"><option value="">Choose…</option>${keys.map((k) => `<option>${esc(k)}</option>`).join("")}</select></div>` : ""}
        <div><label>…or upload one (CSV)</label><input type="file" name="file" accept=".csv"></div>
        <div><label>Account column</label><input type="text" name="account_col" value="account_id" style="width:130px"></div><div><label>Question column</label><input type="text" name="check_col" value="question_ref" style="width:130px"></div>
        <div style="align-self:flex-end"><button class="primary">Score</button></div></form><div id="sr"></div></details>`;
  el.querySelector("#sf").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const out = el.querySelector("#sr"); out.innerHTML = `<p class="muted">Scoring…</p>`;
    try {
      const s = await api(`/api/runs/${runId}/score`, { method: "POST", body: new FormData(ev.target) });
      const row = (l, v, ok, t) => `<tr><td>${l}</td><td class="num"><strong>${v}</strong></td><td><span class="badge ${ok ? "b-completed" : "b-failed"}">${ok ? "PASS" : "FAIL"}</span></td><td class="muted">${t}</td></tr>`;
      const list = (t, a) => (a.length ? `<h3>${t} (${a.length})</h3><p class="mono small">${a.slice(0, 40).map((x) => esc(x.join(" · "))).join("<br>")}</p>` : "");
      out.innerHTML = `<table style="margin-top:14px"><thead><tr><th>Measure</th><th class="num">Result</th><th></th><th>Target</th></tr></thead><tbody>
        ${row("Gap recall", (s.recall * 100).toFixed(1) + `% (${s.matched}/${s.true_gaps})`, s.recall >= 0.95, "≥ 95%")}${row("False-gap rate", (s.false_gap_rate * 100).toFixed(1) + `% (${s.false_gaps.length}/${s.reported_gaps})`, s.false_gap_rate < 0.05, "< 5%")}
        ${row("Claims without a citation", s.unsupported_claims, s.unsupported_claims === 0, "0")}</tbody></table>${list("Missed gaps", s.missed)}${list("False gaps", s.false_gaps)}`;
    } catch (e) { out.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  });
}
