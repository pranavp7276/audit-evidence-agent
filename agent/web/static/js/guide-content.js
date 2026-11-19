/* The in-app guide. Static, trusted HTML. One entry per topic; each is reachable at #/guide/<id>. */
export const GUIDE = [
  { id: "start", title: "Start here", html: `
    <h1>Start here</h1>
    <p>This platform answers a lender's or regulator's audit request on outsourced collections. It reads the request, tests the evidence for every sampled
    loan account, and gives you findings that each point to the records behind them, a gap report, a draft response letter and an evidence pack.</p>
    <h2>Who does what</h2>
    <table><thead><tr><th>Role</th><th>What they do here</th></tr></thead><tbody>
      <tr><td><strong>Compliance reviewer</strong></td><td>Creates the audit, confirms how the request is read, reviews gaps, follows up unknowns, writes management comments, approves the letter.</td></tr>
      <tr><td><strong>Auditor</strong></td><td>Opens an audit question by question, drills into an account, and checks the cited source records.</td></tr>
      <tr><td><strong>Team member</strong></td><td>Maintains the data in the database, the guardrails and the knowledge base, and the code. See <a href="#/guide/data">Working with the data</a> and <a href="#/guide/team">Team setup</a>.</td></tr></tbody></table>
    <h2>The menu</h2>
    <ul>
      <li><strong>Audit work</strong>: <em>Audits</em> lists every audit with its status and review progress; <em>New audit request</em> starts one; <em>Reports</em> gathers what you can hand over for each audit.</li>
      <li><strong>Forms and rules</strong>: <em>Guardrails</em> (what is tested, how serious a failure is, review priority), <em>Compliance library</em> (the circulars and policies they come from) and <em>Rules &amp; data</em> (the limits in force and the data read).</li>
      <li><strong>Help</strong>: this guide. The <em>Data explorer</em> (bottom left) is a read-only SQL box for analysts.</li>
    </ul>
    <h2>Inside an audit</h2>
    <p>An open audit has five tabs that follow the work, left to right: <strong>Overview</strong> (where you are and what is next), <strong>Findings</strong> (by question, the gap register, the follow-up list), <strong>Accounts</strong> (everything tested for one account), <strong>Respond</strong> (the letter, then the evidence pack) and <strong>Agent</strong> (what the agent did, and questions about the results).</p>
    <h2>Every result is one of three</h2>
    <table><thead><tr><th>Result</th><th>Meaning</th></tr></thead><tbody>
      <tr><td><span class="badge b-evidenced">Evidenced</span></td><td>Records prove it. Every evidenced result cites them.</td></tr>
      <tr><td><span class="badge b-gap">Gap</span></td><td>Records show a breach, or a mandatory record is confirmed missing. Always reported, never softened.</td></tr>
      <tr><td><span class="badge b-cannot_determine">Cannot determine</span></td><td>The evidence is missing, unreadable or unclear. The platform makes no claim either way, and it needs follow-up.</td></tr></tbody></table>
    <h2>Try it in five minutes</h2>
    <ol>
      <li>Click your name at the bottom left and enter it. It is recorded on every review and letter change.</li>
      <li>Open <strong>New audit request</strong>, click <em>plain instruction</em> under the text box, then <strong>Read the request</strong>.</li>
      <li>Look at the checks and the period and sample shown, then click <strong>Run audit</strong>.</li>
      <li>When it completes, read the <strong>Summary</strong>, open the <strong>Gap register</strong>, expand a gap, and click <em>View source record</em>.</li>
    </ol>
    <div class="note info">Everything here is synthetic data. Do not load real borrower data.</div>` },

  { id: "audit", title: "Running an audit", html: `
    <h1>Running an audit</h1>
    <h2>1. Upload the request</h2>
    <p>Open <strong>New audit request</strong>. Give it a reference (for example CO-04), who requested it and the response due date. Then either upload the document
    (PDF, .eml or text) or paste its text. There are two accepted forms:</p>
    <table><thead><tr><th>Form</th><th>Example</th></tr></thead><tbody>
      <tr><td><strong>Numbered questions</strong></td><td><pre>Q1. Show consent before every WhatsApp message.
Q2. Confirm calls were within permitted hours.
Severity scale for gaps:
  Critical - borrower impact (Q1, Q2)
Sampled accounts:
CNF123456789, CNF987654321</pre></td></tr>
      <tr><td><strong>A plain instruction</strong></td><td><pre>Run a compliance audit for all accounts reached out
within the previous month. Sample size 300.</pre> Every guardrail is tested unless you name specific ones (for example "check consent and calling hours").</td></tr></tbody></table>
    <p>Sampled accounts are listed by <strong>loan account number</strong> (what an auditor writes) or CN account id.</p>
    <h2>2. Confirm how it is read</h2>
    <p>Click <strong>Read the request</strong>. Nothing runs yet. You see:</p>
    <ul>
      <li><strong>The checks</strong>: each question and the test it maps to. Change the test, set the severity, or <em>Split</em> a question that bundles several tests.
          A question that fits no test is reported as unanswered, never dropped.</li>
      <li><strong>The sample</strong>: how many references matched a loan account. Unmatched and ambiguous references (the same number under two institutions) stay visible and are not tested until resolved.</li>
      <li><strong>The period and sample size</strong> when the request names no accounts: the platform draws a random sample from accounts reached out to in the period.
          The same request always draws the same sample.</li>
    </ul>
    <div class="note">The period is in India calendar days. The start day is included and the end day is not. "Previous month" means the calendar month before today.</div>
    <h2>3. Run</h2>
    <p>Click <strong>Run audit</strong>. A page shows progress. About 60 accounts take roughly a minute; 300 take a few minutes. Audits run one at a time.
    If it fails, the reason is shown at the top of the audit.</p>
    <h2>Where the checks and limits come from</h2>
    <p>Hours, daily limits and notice timelines come from the D12 rules, effective on each event's own date. See <a href="#/rules">Rules &amp; data</a>.</p>` },

  { id: "review", title: "Reviewing results", html: `
    <h1>Reviewing results</h1>
    <p>Open an audit from <strong>Audit requests</strong>. Its tabs, in the order most people use them:</p>
    <h2>Summary</h2>
    <p>The verdict, gaps by severity, where gaps concentrate (collectors and months), and a checklist of what is left to do. Printing this page gives a one-page summary.</p>
    <h2>Questions</h2>
    <p>Each question as it was read, how it was tested and its result. Click <em>Open findings</em> to see every result for that question. This is also where you write the <strong>management comment</strong> for each question.</p>
    <h2>Gap register</h2>
    <ol>
      <li>Gaps are listed most severe first, then by guardrail priority weight.</li>
      <li>Click a gap to open it. You see the test applied, the records it cites (with UTC time and the time as written in the source) and <em>View source record</em> for the raw row.</li>
      <li>Record your decision: <strong>Confirmed</strong>, <strong>Disputed</strong> (a reason is required) or <strong>Remediation planned</strong> (a reason is required).
          Use the checkboxes to apply one decision to many gaps.</li>
    </ol>
    <div class="do"><strong>A dispute never removes a gap.</strong> It adds your note. The gap stays in the register, the summary, the letter and the pack until the underlying evidence changes.</div>
    <h2>Follow-up</h2>
    <p>Everything the platform could not determine, with the reason: a recording that could not be read, no transcript, a notice not yet due, a collector with no employee code.
    Get the evidence, then record <strong>Evidence obtained</strong>. Until then these stay open and no compliance is claimed for them.</p>
    <h2>Accounts and the account file</h2>
    <p>Search the sampled accounts. Open one to see every call, message, consent, recording and notice on one timeline in UTC, with the source time beside it.
    Events cited by a gap are red; events cited by a cannot-determine finding are amber. Unmatched and ambiguous references are listed here too.</p>
    <h2>Reading a finding</h2>
    <table><thead><tr><th>Part</th><th>What it tells you</th></tr></thead><tbody>
      <tr><td>Reason</td><td>One sentence stating what was found, with the dates and counts.</td></tr>
      <tr><td>Records</td><td>The exact records behind it. The first is the primary record; the rest are supporting (the rule, the consent, the recording status).</td></tr>
      <tr><td>Severity</td><td>From the request's own scale when it gave one; otherwise the guardrail's default.</td></tr>
      <tr><td>Priority</td><td>Shown only when above 1. It sets review order and nothing else.</td></tr></tbody></table>` },

  { id: "response", title: "Letter and evidence pack", html: `
    <h1>Letter and evidence pack</h1>
    <h2>Management comments</h2>
    <p>On the <strong>Questions</strong> tab, write the comment for each question: root cause, remediation and timeline. The platform never writes these for you.
    They appear in the letter under each question.</p>
    <h2>The response letter</h2>
    <ol>
      <li>Open <strong>Response letter</strong>. It is generated from the findings, your reviews and your comments. Every figure comes from a recorded finding.</li>
      <li>Edit it in the left box; the right side previews it. <strong>Save draft</strong> keeps a version.</li>
      <li>Move it to <strong>Send for compliance review</strong>, then <strong>Approve</strong>. Approval is blocked while any <em>[To be completed by management]</em> placeholder remains.</li>
      <li>If findings or comments change later, click <strong>Regenerate from findings</strong>. Earlier versions stay in the version list.</li>
      <li><strong>Print / save as PDF</strong> prints the preview.</li>
    </ol>
    <h2>The evidence pack</h2>
    <p>The <strong>Evidence pack</strong> tab downloads a zip, rebuilt from the current state each time:</p>
    <table><thead><tr><th>File</th><th>Contents</th></tr></thead><tbody>
      <tr><td>index.md</td><td>Each check with its counts and a link to its extract</td></tr>
      <tr><td>extracts/&lt;check&gt;.csv</td><td>One row per finding with its cited records and review status</td></tr>
      <tr><td>gap_report.csv</td><td>Every gap by severity and priority, with the decision taken</td></tr>
      <tr><td>follow_up.csv</td><td>Everything that could not be determined</td></tr>
      <tr><td>reviews.csv</td><td>Who decided what, and when</td></tr>
      <tr><td>response_letter.md</td><td>The latest saved letter</td></tr>
      <tr><td>rules_and_assumptions.md</td><td>What each check tests and the interpretations used</td></tr></tbody></table>
    <p>The same tab has a <em>Quality check</em>: score the audit against a known gap key (recall, false gaps, claims without a citation).</p>
    <div class="note">Audits are frozen once completed. To test changed data or a changed guardrail, run a new audit.</div>` },

  { id: "agent", title: "How the agent works", html: `
    <h1>How the agent works</h1>
    <p>When you start an audit, an agent does the testing. It follows the same fixed order every time, so you can predict what it did and check it in the <strong>Agent activity</strong> tab.</p>
    <table><thead><tr><th>Step</th><th>Who</th><th>What happens</th></tr></thead><tbody>
      <tr><td>1. Read</td><td>Parser</td><td>Splits the request into questions, finds the period and sample size, and shows you how it read them. You confirm before anything runs.</td></tr>
      <tr><td>2. Plan</td><td>Planner</td><td>For each check, lists which sources will be read, which guardrail version applies, and what is assumed (for example a default severity).</td></tr>
      <tr><td>3. Retrieve</td><td>Retriever</td><td>Reads the call log, messages, recordings, transcripts, consent, notices, certification and the D12 rules. Read-only.</td></tr>
      <tr><td>4. Evaluate</td><td>Checks</td><td>Apply the rule to each call, message or notice. The result is evidenced, gap or cannot determine, with the records cited. No model decides this.</td></tr>
      <tr><td>5. Investigate</td><td>Investigator</td><td>Where a result rests on missing evidence, it retries a failed account and looks for a recording or transcript under the same call logged by the other dialer, then runs the same check again. What it cannot settle stays <em>cannot determine</em> and goes to Follow-up.</td></tr>
      <tr><td>6. Report</td><td>Reporter</td><td>Saves findings and citations, the activity log, and builds the letter and pack.</td></tr></tbody></table>
    <h2>Limits that keep it honest</h2>
    <ul><li>A gap is never hidden or softened by the investigator; it can only turn up evidence that was in another system.</li>
      <li>Missing evidence is never counted as a pass.</li><li>The search is bounded: two retries per failed account and one lookup per call.</li>
      <li>A <strong>second reading</strong>: a second model reads each sampled gap against only the records it cites and says whether they support it. It never changes a gap; a disagreement moves it to the top of your review queue.</li>
      <li>The <strong>letter claims check</strong>: every statement of fact in the response letter carries a reference ([F123] a finding, [Q3] a check) and its numbers must match the findings, or the letter cannot be approved.</li>
      <li><strong>Questions are sorted first</strong>: a question for an agency document (a contract, a licence, insurance) is listed for the agency to supply, and a question no system can show is reported as cannot determine. Neither is ever marked evidenced.</li>
      <li><strong>Ask the audit</strong> answers from this audit's findings only and cannot cite a finding it did not retrieve.</li></ul>
    <p>The same steps, with a diagram, are in <code>docs/workflow.md</code>.</p>` },
  { id: "guardrails", title: "Guardrails and weights", html: `
    <h1>Guardrails and weights</h1>
    <p>A <strong>guardrail</strong> is one testable obligation, such as "calls only inside the calling window". The platform ships with seven, one per check.</p>
    <h2>Knowledge base to guardrail</h2>
    <ol>
      <li>In <strong>Knowledge base</strong>, add a circular, policy or SOP (PDF, text or pasted). It is split into numbered clauses.</li>
      <li>Open the document and click <strong>Suggest guardrails from the clauses</strong>. Draft guardrails appear, each linked to its clause and with any limits it states (for example 8:00 to 18:50, five attempts a day).
          Suggestions are keyword based: treat them as a starting point.</li>
      <li>In <strong>Guardrails</strong>, open a draft, correct it, and set <em>Status</em> to <strong>published</strong> with an effective date.</li>
    </ol>
    <h2>Three separate ideas</h2>
    <table><thead><tr><th>Idea</th><th>What it controls</th><th>Set by</th></tr></thead><tbody>
      <tr><td>Outcome</td><td>Evidenced, gap or cannot determine</td><td>The evidence and the test only</td></tr>
      <tr><td>Severity</td><td>How serious a confirmed gap is</td><td>The request's own scale; otherwise the guardrail default</td></tr>
      <tr><td>Priority weight (1 to 3)</td><td>Which controls reviewers look at first</td><td>Compliance, with a recorded reason for anything above 1</td></tr></tbody></table>
    <div class="do">A weight never hides, softens or removes a gap. It only changes the order of the review queue.</div>
    <h2>Versions</h2>
    <p>Editing a guardrail saves a <strong>new version</strong>; older versions stay in the history. Each audit records the guardrail id and version it applied. If two published
    guardrails cover the same control, the one with the latest effective date (on or before today) is used.</p>
    <div class="note">The tests read their limits from the D12 rule rows in the database, not from the guardrail text. Limits typed into a guardrail are for reference. To change a limit,
    add a D12 rule row with a new effective date (see <a href="#/guide/data">Working with the data</a>).</div>` },

  { id: "data", title: "Working with the data", html: `
    <h1>Working with the data</h1>
    <p>The platform tests a replica of the CN Core collections schema in a shared Supabase Postgres: delinquent loans of three fictional lenders (a bank, an NBFC and an MFI) with 12 months of history. All data is synthetic. Table names are CN Core's; to query the data with the sandbox's D1 to D13 field names, use the <code>book</code> schema.</p>
    <h2>Where things are</h2>
    <table><thead><tr><th>Schema</th><th>Holds</th></tr></thead><tbody>
      <tr><td><code>cn_core</code></td><td>Customers, loan accounts, cases, contact numbers, the call-status log, activity log, message log, templates</td></tr>
      <tr><td><code>uamdb</code></td><td>Organisations, users (collectors) and roles</td></tr>
      <tr><td><code>compliance</code></td><td>Consent, certification, D12 rules, holidays, recordings, transcripts, notices, dialer config</td></tr>
      <tr><td><code>audit</code></td><td>Audit runs, findings, citations, reviews, letters, guardrails, knowledge base</td></tr>
      <tr><td><code>staging</code></td><td>Views the agent reads (UTC timestamps). Read-only</td></tr>
      <tr><td><code>book</code></td><td>The sandbox view of the data: <code>d1_account_master</code>, <code>d2_borrower_master</code>, <code>d4_contact_history</code>, <code>d5_call_transcripts</code>, <code>d10_consent_dnd</code>, <code>d11_template_registry</code> and <code>d12_policy_library</code> with the sandbox's own field names (read-only views; the datasets no audit check reads were removed)</td></tr>
      <tr><td><code>sandbox</code></td><td>Your own scratch tables</td></tr></tbody></table>
    <p>In the Supabase <strong>Table Editor</strong>, the schema is chosen from the dropdown at the top left. It opens on <code>public</code>, which is empty.</p>
    <h2>What to add so a check can see it</h2>
    <table><thead><tr><th>To test</th><th>Add rows to</th></tr></thead><tbody>
      <tr><td>A call</td><td><code>cn_core.tele_process_instance_call_logs</code> (one row per status event; same <code>dialer_code</code> and <code>call_session_id</code>; time in that dialer's own zone) <strong>and</strong> <code>cn_core.tele_process_instance_activity</code> (links the session to the account). Without the second, the call does not appear.</td></tr>
      <tr><td>A connected call's recording and identity check</td><td><code>compliance.call_recording</code> (AVAILABLE, NOT_FOUND or RETRIEVAL_FAILED) and, if available, <code>compliance.call_transcript_segment</code> rows tagged IDENTITY_CHECK_PASS, DUES_DISCLOSURE etc. with offsets</td></tr>
      <tr><td>A message and its consent</td><td><code>cn_core.communication_dashboard_t</code> (recipient in <code>sms_contact_no</code>, <code>template_id</code>) and <code>compliance.customer_consent</code> for the same number and channel (UTC)</td></tr>
      <tr><td>A notice</td><td><code>compliance.notice</code> (trigger, dispatch and served dates)</td></tr>
      <tr><td>A collector's certificate</td><td><code>compliance.collector_certification</code>, keyed by the user's <code>employee_code</code></td></tr>
      <tr><td>A collector's status (active, inactive, terminated)</td><td><code>compliance.collector_status</code>, with <code>valid_from</code> and <code>valid_to</code></td></tr>
      <tr><td>A number an agency may call from</td><td><code>compliance.registered_cli</code>; the call's own number is <code>user_contact_number</code> on the call log</td></tr>
      <tr><td>When a template was approved or retired</td><td><code>approved_at</code> and <code>retired_at</code> on <code>cn_core.digital_template</code></td></tr>
      <tr><td>A change in a limit</td><td>A new row in <code>compliance.calling_policy_rule</code> with an <code>effective_from</code> date and, for hours and daily caps, the lender's <code>institution_code</code> (BANK01, NBFC01 or MFI01); set an <code>effective_to</code> on the row it replaces</td></tr></tbody></table>
    <h2>Time zones</h2>
    <p>SlashRTC call times are IST, CognifAI call times are UTC, the message log is IST, consent is UTC. Enter each in its own source's zone. The platform converts to UTC for comparison and shows both.</p>
    <h2>After you change data</h2>
    <p>The views are live, so a new audit sees your rows straight away. Existing audits do not change: run a new one.</p>
    <div class="do"><strong>Do:</strong> use synthetic data; keep rows consistent across tables; put experiments in <code>sandbox</code>.</div>
    <div class="dont"><strong>Do not:</strong> run <code>scripts/gen_book.py</code> or <code>migrate.py --reset</code> against the shared database (they replace everyone's data and refuse to run without a deliberate override); edit an existing migration file; load real borrower data.</div>` },

  { id: "team", title: "Team setup", html: `
    <h1>Team setup</h1>
    <h2>Connect your machine</h2>
    <ol>
      <li>Open the repo (branch <code>synthetic-data-and-agent</code> or its successor) and create an environment:
        <pre>python -m venv .venv
.venv\\Scripts\\activate
pip install -e ".[dev]"</pre></li>
      <li>Copy <code>.env.example</code> to <code>.env</code> and set <code>DATABASE_URL</code> to the <code>audit_team</code> connection string the owner gives you. Never commit <code>.env</code>.</li>
      <li>Check: <code>python -m pytest -q</code> should pass, then start the platform: <code>python -m agent serve</code> and open <code>http://127.0.0.1:8000</code>.</li>
    </ol>
    <p>Everyone's copy of the platform reads and writes the same database, so you all see the same audits, guardrails and reviews.</p>
    <h2>What your login can do</h2>
    <table><thead><tr><th>Can</th><th>Cannot</th></tr></thead><tbody>
      <tr><td>Read everything; add, change and delete rows in <code>cn_core</code>, <code>uamdb</code>, <code>compliance</code>; run audits; create tables in <code>sandbox</code></td>
          <td>Drop, alter or truncate tables; create tables in the shared schemas; delete audit findings; create logins</td></tr></tbody></table>
    <h2>Working agreements</h2>
    <ul>
      <li><strong>Structure changes</strong> (a new table or column) are a new migration file <code>db/migrations/V0NN__name.sql</code> in a pull request. The owner applies it. Never edit one that already exists.</li>
      <li><strong>Rules of the platform</strong> (in <code>CLAUDE.md</code>): no claim without a cited record; gaps are never dropped or softened; compare time in UTC; limits come from D12 rows; judgement lives in code, not in prose.</li>
      <li><strong>Decisions</strong> that change how a check judges evidence go in <code>docs/decisions.md</code>.</li>
      <li>Run <code>python -m pytest -q</code> and <code>python -m ruff check .</code> before you push.</li>
      <li>Your name (bottom left) is recorded on reviews, comments, letters and guardrail changes. Use your own.</li>
    </ul>
    <h2>If you use Claude Code</h2>
    <p>Paste the onboarding prompt from <code>docs/team_onboarding.md</code> into your Claude chat; it sets up the connection and repeats these rules.</p>` },

  { id: "help", title: "Troubleshooting", html: `
    <h1>Troubleshooting</h1>
    <table><thead><tr><th>You see</th><th>Why, and what to do</th></tr></thead><tbody>
      <tr><td>The tables look empty in Supabase</td><td>The Table Editor opens on the <code>public</code> schema. Switch the schema dropdown to <code>cn_core</code>, <code>compliance</code>, <code>uamdb</code> or <code>audit</code>. Views are in <code>staging</code>.</td></tr>
      <tr><td>"No checks could be made from this request"</td><td>The text has no numbered questions (Q1, Q2) and no recognisable topic. Say what to test, e.g. "check consent and calling hours for last month", or number the questions.</td></tr>
      <tr><td>The audit shows <em>failed</em></td><td>The reason is at the top of the audit page. Common causes: none of the account references matched, or the period had no contacts.</td></tr>
      <tr><td>Some references are unmatched or ambiguous</td><td>Unmatched: the number is not a loan account (check the typo). Ambiguous: the same number exists under two institutions. Both are listed in the Accounts tab and are not tested.</td></tr>
      <tr><td>Lots of "cannot determine"</td><td>Expected where evidence is missing: unreadable recordings, no transcript, notices not yet due, collectors with no employee code. Work through the Follow-up tab.</td></tr>
      <tr><td>A change to a guardrail has no effect</td><td>Its status must be <em>published</em> and its effective date on or before today. Audits already run keep the version they applied.</td></tr>
      <tr><td>A change to the data does not show in an audit</td><td>Existing audits are frozen. Run a new one. Check the row has all its linked rows (see <a href="#/guide/data">Working with the data</a>).</td></tr>
      <tr><td>The page asks for a password</td><td>The platform was started with <code>APP_PASSWORD</code>. Use any user name and the password the owner gave you.</td></tr>
      <tr><td>Cannot connect to the database</td><td>Check <code>DATABASE_URL</code> in <code>.env</code> is the session pooler address (port 5432) and the password is right. Port 6543 will not work. If port 5432 is blocked on your network, tell the owner.</td></tr>
      <tr><td>"Address already in use" on start</td><td>Another copy is running. Start on another port: <code>python -m agent serve --port 8001</code>.</td></tr>
      <tr><td>A page shows "Loading…" or an error</td><td>Refresh once. If it persists, note the message and tell the owner; the server log shows the cause.</td></tr></tbody></table>` },

  { id: "glossary", title: "Glossary", html: `
    <h1>Glossary</h1>
    <table><thead><tr><th>Term</th><th>Meaning</th></tr></thead><tbody>
      <tr><td>Audit request</td><td>The lender's or regulator's request: questions, a sample of accounts, a period, a severity scale.</td></tr>
      <tr><td>Account reference</td><td>How the auditor names a loan, normally the loan account number. It is matched to a CN account.</td></tr>
      <tr><td>CN account id</td><td>The internal key of a loan account in CN Core.</td></tr>
      <tr><td>Check</td><td>One testable control applied to the sample, for example calling hours.</td></tr>
      <tr><td>Guardrail</td><td>The approved, versioned definition of an obligation: source, severity, weight.</td></tr>
      <tr><td>Finding</td><td>The result of a check for one account (or one event), with its cited records.</td></tr>
      <tr><td>Citation</td><td>A pointer to the exact source record a statement rests on.</td></tr>
      <tr><td>Call session</td><td>One call, identified by its dialer and session id. It can have several status rows (for example connected, then disposed) and still counts once.</td></tr>
      <tr><td>Dialer</td><td>The system that places calls. Here SlashRTC (times in IST) and CognifAI (times in UTC).</td></tr>
      <tr><td>Mirrored call</td><td>The same call logged by both dialers. It counts once, under the dialer the cross-reference names.</td></tr>
      <tr><td>Eligible attempt</td><td>An outbound call session that is not a system failure. Attempts to one contact number in one day are counted against the daily cap.</td></tr>
      <tr><td>D12</td><td>The policy rules for calling hours, daily attempts and notice timelines. Each rule has an effective date range.</td></tr>
      <tr><td>Effective-dated rule</td><td>A rule applies to events on or after its start date and before its end date. Each event is tested against the rule in force on its own day.</td></tr>
      <tr><td>Severity</td><td>How serious a confirmed gap is, on the request's scale (for example Critical, Major, Minor).</td></tr>
      <tr><td>Priority weight</td><td>1 to 3. Orders review only.</td></tr>
      <tr><td>Disposition (review)</td><td>Your decision on a finding: open, confirmed, disputed, remediation planned, evidence obtained.</td></tr>
      <tr><td>Frozen audit</td><td>A completed audit whose findings cannot be changed. A new audit is a new record.</td></tr>
      <tr><td>Evidence pack</td><td>The zip of the index, extracts, gap report, follow-up list, review trail, letter and rules.</td></tr></tbody></table>` },
];
