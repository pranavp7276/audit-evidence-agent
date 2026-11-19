import { app, post, esc, num } from "../core.js";

const SAMPLES = [
  ["Rows per source", `SELECT 'Call sessions' AS source, count(*) AS rows FROM staging.call_sessions
UNION ALL SELECT 'Messages', count(*) FROM staging.messages
UNION ALL SELECT 'Consents', count(*) FROM staging.consents
UNION ALL SELECT 'Recordings', count(*) FROM staging.recordings
UNION ALL SELECT 'Transcript segments', count(*) FROM staging.transcript_segments
UNION ALL SELECT 'Notices', count(*) FROM staging.notices`],
  ["Calls after the window closes (rule in force that day)", `SELECT s.account_id, s.session_key, s.started_ts_src, s.started_ts_src_tz, (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::time AS local_time, r.rule_value AS window_end
FROM staging.call_sessions s JOIN staging.policy_rules r ON r.rule_key = 'calling_window_end'
 AND (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date >= r.effective_from AND ((s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date < r.effective_to OR r.effective_to IS NULL)
WHERE s.counts_as_attempt AND NOT s.is_mirror_duplicate AND (s.started_ts_utc AT TIME ZONE 'Asia/Kolkata')::time >= r.rule_value::time ORDER BY s.started_ts_utc LIMIT 50`],
  ["Contact numbers called over the cap in a day", `SELECT contact_no, (started_ts_utc AT TIME ZONE 'Asia/Kolkata')::date AS day, count(*) AS attempts
FROM staging.call_sessions WHERE counts_as_attempt AND NOT is_mirror_duplicate GROUP BY 1, 2 HAVING count(*) >= 5 ORDER BY attempts DESC, day LIMIT 50`],
  ["Sessions logged by both dialers (mirrors)", `SELECT account_id, session_key, mirror_of, started_ts_src, started_ts_src_tz FROM staging.call_sessions WHERE is_mirror_duplicate ORDER BY started_ts_utc LIMIT 50`],
  ["Connected calls the recording store cannot confirm", `SELECT s.account_id, s.session_key, r.storage_status, r.note FROM staging.call_sessions s
JOIN staging.recordings r ON r.session_key = s.session_key WHERE s.connected AND r.storage_status <> 'AVAILABLE' ORDER BY s.started_ts_utc LIMIT 50`],
];
export async function sqlPage() {
  app.innerHTML = `<h1>Data explorer</h1><p class="muted">For analysts: run a read-only SELECT against the loaded data (staging views are in UTC). Same read-only warehouse tool the agent uses.</p>
    <div class="card"><div class="row"><div style="flex:1;min-width:240px"><label for="samp">Sample queries</label><select id="samp">${SAMPLES.map(([n], i) => `<option value="${i}">${esc(n)}</option>`).join("")}</select></div>
      <div style="align-self:flex-end"><button class="primary" id="go">Run query</button></div></div>
      <label for="q" style="margin-top:12px">Query</label><textarea id="q" spellcheck="false" style="min-height:160px"></textarea></div><div id="res"></div>`;
  const q = document.getElementById("q"), samp = document.getElementById("samp");
  const run = async () => {
    const res = document.getElementById("res"); res.innerHTML = `<div class="card muted">Running…</div>`;
    try {
      const r = await post("/api/sql", { query: q.value });
      res.innerHTML = `<div class="card"><div class="muted small">${num(r.rows.length)} rows${r.truncated ? " (truncated)" : ""}</div>${r.rows.length ? `<div style="overflow:auto;max-height:520px"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${r.rows.map((row) => `<tr>${row.map((v) => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">No rows.</div>`}</div>`;
    } catch (e) { res.innerHTML = `<div class="err">${esc(e.message)}</div>`; }
  };
  samp.onchange = () => { q.value = SAMPLES[+samp.value][1]; run(); };
  document.getElementById("go").onclick = run; q.value = SAMPLES[0][1]; run();
}
