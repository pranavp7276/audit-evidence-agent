# Context for AI coding assistants (Claude Code, Cursor, etc.)

Read this before changing anything. Humans: this is the short version of CONTRIBUTING.md.

## What we are building
An agent that reads an audit request on outsourced collections (PDF or email), splits it into
checks, tests evidence per sampled account, and produces an evidence pack, a gap report graded
on the request's severity scale, and a draft response letter. Full brief: docs/problem.md.
Scored on hidden requests: gap recall >= 95%, false gaps < 5%, zero claims without a citation.

## Non-negotiable rules
1. **No claim without a cited record.** A Finding with status `evidenced` or `gap` must carry at
   least one Citation. If evidence is missing or ambiguous, the status is `cannot_determine`.
   This is enforced in `agent/contracts.py` and again by a database trigger. Never work around it.
2. **Never drop or soften a gap.** Do not filter, merge away or reword gaps to look better.
3. **Compare timestamps only in UTC**, using `*_utc` columns from `staging`. Sources use
   different time zones on purpose. Never parse raw timestamps in Python.
4. **Layers:** `raw` = files as provided (all TEXT, owned by the loader). `staging` = typed views,
   UTC (db/staging/R__*.sql). `audit` = agent output (db/migrations). Tools read `staging` only.
5. **Migrations are append-only.** Never edit a `db/migrations/V###__*.sql` file that exists on
   `main`; add a new one with the next free number. Staging files (`R__*`) may be edited.
6. **Contracts are shared.** Changing `agent/contracts.py` or `docs/contracts.md` needs a note in
   `docs/decisions.md` and review from every module owner.
7. **Calling hours and frequency limits come from D12.** Never hard-code them.
8. **Data minimisation.** Citation `extract` holds only the fields the request needs.
9. **Judgement in code, not prose.** The LLM chooses checks and parameters; pass/fail is
   decided by deterministic code in `agent/checks/`.
10. **Business rules live in docs/decisions.md.** If you have to pick an interpretation
    (same-timestamp consent, which zone calling hours use, holiday rules), do not decide it
    silently in code: check decisions.md, and if it is not there, stop and ask.

## Where things are
- `agent/contracts.py` types every module exchanges (CheckSpec, Finding, Citation)
- `agent/tools/` the 7 mandated tools; `agent/checks/` one module per check type
- `agent/store.py` the only code that writes to the database
- `eval/score.py` scorer; run it before and after any change to checks
- `docs/data_dictionary.md` columns, keys and time zone of every source

## Commands
`make setup` (first time), `make test`, `make lint`, `make eval RUN=<id> KEY=<gap key csv>`

## Domain references (from real audit documents; only what applies here)
- Precedence when sources disagree: audit request (wording, sample, severity scale) > D12 (calling hours and frequency) > guardrail defaults > RBI baseline (calls only 08:00 to 19:00, no persistent calling). Never hard-code the window or daily caps; read them from D12.
- Normalise all timestamps to Asia/Kolkata before any hour, day or date comparison.
- Triage each request question first: a per-account check we can test, a vendor document (agency artefacts such as contracts, licences, insurance, CCTV, business continuity plan: never evidenced from our data, listed for the agency to supply), or not testable from any system (dress code, visit location, gifts: always `cannot_determine`, said plainly in the letter).
- A missing recording makes the transcript-based checks for that call `cannot_determine`, never `evidenced`.
- Quality-scorecard "fatal" items (recording disclaimer, false information, disposition mismatch, threats) map to the top of the request's severity scale unless the scale says otherwise. Soft-skill scoring (greeting, negotiation, dead air) is not audit compliance.
- Keep borrower detail in pack outputs to what the request needs: account reference, dates, record ids. No names or full phone numbers unless the request asks.
- The agent's own loop and roles: docs/workflow.md.

