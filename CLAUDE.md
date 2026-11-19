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
   This is enforced in `agent/core/contracts.py` and again by a database trigger. Never work around it.
2. **Never drop or soften a gap.** Do not filter, merge away or reword gaps to look better.
3. **Compare timestamps only in UTC**, using `*_utc` columns from `staging`. Sources use
   different time zones on purpose. Never parse raw timestamps in Python.
4. **Layers:** `raw` = files as provided (all TEXT, owned by the loader). `staging` = typed views,
   UTC (db/staging/R__*.sql). `audit` = agent output (db/migrations). Tools read `staging` only.
5. **Migrations are append-only.** Never edit a `db/migrations/V###__*.sql` file that exists on
   `main`; add a new one with the next free number. Staging files (`R__*`) may be edited.
6. **Contracts are shared.** Changing `agent/core/contracts.py` or `docs/contracts.md` needs a note in
   `docs/decisions.md` and review from every module owner.
7. **Calling hours and frequency limits come from D12.** Never hard-code them.
8. **Data minimisation.** Citation `extract` holds only the fields the request needs.
9. **Judgement in code, not prose.** The LLM chooses checks and parameters; pass/fail is
   decided by deterministic code in `agent/checks/`.
10. **Business rules live in docs/decisions.md.** If you have to pick an interpretation
    (same-timestamp consent, which zone calling hours use, holiday rules), do not decide it
    silently in code: check decisions.md, and if it is not there, stop and ask.

## Where things are
- `agent/core/contracts.py` types every module exchanges (CheckSpec, Finding, Citation)
- The code is six layers, each importing only from layers below it (enforced by `tests/test_architecture.py`): core, tools, checks/intake/knowledge, runtime, services, web. See `docs/architecture.md` before adding a module.
- `agent/tools/` the data sources the agent reads; `agent/checks/` one module per check type; `agent/runtime/` the agent (never writes)
- `agent/services/store.py` the only code that writes to the database
- `eval/score.py` scorer; run it before and after any change to checks
- `docs/data_dictionary.md` columns, keys and time zone of every source

## Commands
`make setup` (first time), `make test`, `make lint`, `make eval RUN=<id> KEY=<gap key csv>`

## Domain references (real audit documents)

- **Build plan: `docs/BUILD_PLAN.md`.** Its milestones (M0 to M7) and rules are the reference; `PROGRESS.md` says where the repository stands against them. The repository keeps its staging-view architecture (docs/architecture.md, D-028) instead of the plan's `ledger.*` and `evidence.*` schemas.
- Evidence tagging spec: `config/evidence_tags.yaml`. It lists the fields, the Y/N/U flags and the transcript tags per activity (call, field visit, message, notice, payment) and per master. Flag codes (`F_*`, `T_*`) and reason codes in code match it. `python -m agent tags` checks it against the database and writes `docs/evidence_coverage.md`.
- Column names come from `config/source_map.yaml`. Never guess them.
- Rule catalog: `config/check_catalog.yaml`. This is the single source for check IDs (HRS-01, FRQ-01, CNS-01, VER-01, CRT-01, NOT-01, ...), their evidence sources and their tests. When adding a check, add it here first and reference its `id` in code and tests.
- Background: `docs/reference/README.md`.
- Precedence: audit request (wording, sample, severity scale) > D12 (calling hours and frequency) > catalog `defaults` > RBI baseline. Never hard-code 08:00-19:00 or the 10/20 daily caps in logic; read them from D12 and fall back to the catalog.
- Normalise all timestamps to Asia/Kolkata before any hour, day or date comparison.
- Verdicts are only `evidenced | gap | cannot_determine`. Every verdict cites record IDs. `evidenced` without a cited record is a bug. Missing data gives `cannot_determine`, never `evidenced`.
- Triage every request question first: account_check / vendor_document / not_testable (see header of the catalog). Vendor documents are never evidenced from our data; list them for the agency to supply.
- Agency answers (status, remarks, 'NA') are claims, not evidence. Test them against data before accepting. Letters say Compliant / Gap / Cannot determine, never bare Yes/No.
- Items listed under `not_testable_from_systems` are always `cannot_determine` and must be stated plainly in the response letter.
- Keep borrower PII in pack outputs to what the request needs: account ref, dates, record IDs. Keep names and phone numbers out unless the request asks for them.
- The database holds only what an audit check or a sandbox dataset the problem statement names (D1, D2, D4, D5, D10, D11, D12) needs; a column or table nothing reads is removed, not kept "just in case" (D-029).
