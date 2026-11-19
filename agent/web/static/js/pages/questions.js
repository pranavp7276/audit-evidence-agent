import { api, esc, num, when, info, sevBadge, stackBar, needName } from "../core.js";

export async function questionsTab(el, d, runId, scale) {
  const resp = await api(`/api/runs/${runId}/responses`);
  const groups = {};
  d.checks.forEach((c) => (groups[c.question_ref] ||= []).push(c));
  el.innerHTML = `<p class="muted">Each question as the platform read it, how it was tested, and the result. Add the management comment that will appear in the response letter.</p>` +
    Object.entries(groups).map(([ref, cs]) => {
      const r = resp[ref];
      return `<div class="qcard"><div class="qh"><div class="row between"><div><strong>${esc(ref)}</strong> &nbsp;${esc(cs[0].question_text)}</div><a class="btn" href="#/run/${runId}/questions/${encodeURIComponent(ref)}">Open findings</a></div></div>
        <div class="qb"><div>${cs.map((c) => {
          const i = info(c.check_type);
          return `<div class="interp"><b>${esc(c.check_id)} · ${esc(i.title)}</b>${c.test_definition && c.test_definition.severity ? ` &nbsp;${sevBadge(c.test_definition.severity, scale)}` : ""}${c.test_definition && c.test_definition.guardrail ? ` <span class="tag" title="The guardrail version this audit applied">guardrail ${esc(c.test_definition.guardrail.id)} v${esc(c.test_definition.guardrail.version)}${c.test_definition.priority_weight > 1 ? ` · priority ${esc(c.test_definition.priority_weight)}` : ""}</span>` : ""}<br>${esc(i.tests)}
            <div class="small muted" style="margin-top:4px">Gap when: ${esc(i.gap)}<br>Sources: ${(i.sources || []).map(esc).join(", ") || "none"}</div></div>
            <div style="margin:8px 0 14px">${c.check_type === "other" ? `<div class="note">Not testable by the platform: this question will be reported as unanswered and needs a manual response.</div>` : `${stackBar(+c.accounts_ok, +c.accounts_gap, +c.accounts_unknown)}<div class="small muted">${num(c.accounts_ok)} compliant · <strong style="color:var(--gap)">${num(c.accounts_gap)} with gaps</strong> · ${num(c.accounts_unknown)} cannot determine (of ${num(c.accounts)} sampled)</div>`}</div>`;
        }).join("")}</div>
        <div><label for="mc-${esc(ref)}">Management comment (goes into the letter)</label>
          <textarea id="mc-${esc(ref)}" data-ref="${esc(ref)}" style="min-height:130px;font-family:inherit" placeholder="Explain root cause, remediation and timelines for the gaps in this question.">${esc(r ? r.body : "")}</textarea>
          <div class="row" style="margin-top:8px"><button class="primary" data-save="${esc(ref)}">Save comment</button><span class="small muted" data-msg="${esc(ref)}">${r ? `Last saved by ${esc(r.author)} on ${when(r.created_at)}` : "Not yet written"}</span></div></div></div></div>`;
    }).join("");
  el.querySelectorAll("[data-save]").forEach((b) => b.addEventListener("click", async () => {
    const ref = b.dataset.save, who = needName(); if (!who) return;
    const msg = el.querySelector(`[data-msg="${ref}"]`);
    try {
      await api(`/api/runs/${runId}/responses/${encodeURIComponent(ref)}`, { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ body: el.querySelector(`textarea[data-ref="${ref}"]`).value, author: who }) });
      msg.textContent = `Saved by ${who} just now`;
    } catch (e) { msg.innerHTML = `<span class="badge b-failed">${esc(e.message)}</span>`; }
  }));
}
