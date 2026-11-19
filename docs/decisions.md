# Decision log

One entry per ruling. Newest at the bottom. Code that implements a decision cites its id.
Status: **agreed**, **proposed** (default until the team confirms in a sync), **superseded by D-xxx**.

| ID | Date | Decision | Why | Status |
|---|---|---|---|---|
| D-001 | 2026-11-19 | Postgres 16 with three schemas: raw, staging, audit | Keep source data untouched, normalise once, keep agent output separate and auditable | proposed |
| D-002 | 2026-11-19 | Every timestamp is compared in UTC via staging `*_utc` columns; original value and assumed zone kept in `*_src`, `*_src_tz` | Sources differ in time zone by design; one place to get it right | proposed |
| D-003 | 2026-11-19 | Raw tables are loaded with all columns as TEXT plus `_row_no` | Nothing coerced silently; `_row_no` gives every record a citable key | proposed |
| D-004 | 2026-11-19 | `evidenced` and `gap` findings both require at least one citation; otherwise `cannot_determine` | "No compliance claim without a cited record"; a gap is a claim too, cite the record that shows it | proposed |
| D-005 | 2026-11-19 | The pack and letter are generated only from audit.* rows | Every statement traceable to a record | proposed |
| D-006 | 2026-11-19 | False-gap rate = reported gaps not in the key / all reported gaps, at (account, question) level | Our reading of "false gaps under 5%"; confirm with organisers | proposed |
| D-007 | 2026-11-19 | Pass/fail is decided by deterministic code; the LLM picks checks and parameters | Same evidence always gives the same answer; easier to debug and defend | proposed |

## Open questions (settle, then move into the table)
- Consent with exactly the same timestamp as the message: before or not?
- Calling hours: measured in the borrower's local time, the collector's, or the system's? What does D12 say?
- Calling frequency: per calendar day in which zone; attempts or connects?
- Notice timeline: which date counts as "served"; national only or national + borrower's state holidays?
- Certification: is the call date taken in IST or the register's zone; is the expiry date inclusive?
- A series of calls with one recording missing: gap on that call only, or on the series?
- Granularity of the gap keys: per account per question, or per event?
| D-008 | 2026-11-19 | Synthetic dataset (scripts/gen_synthetic_data.py, seed 42) stands in for the organisers' files. Assumed roles: D4 contact log, D5 consent registry, D10 recording store, D11 identity verification, D12 policy limits | The real D5/D10/D11 layouts are not available; the problem statement names the evidence types but not the sources | proposed |
| D-009 | 2026-11-19 | Synthetic zones: D4, D10 and notice dates are Asia/Kolkata (naive local); D5 and D11 are UTC (explicit Z). Calling hours [08:00, 19:00) and 3 calls/day are measured in IST (all synthetic borrowers are in India); consent or verification at exactly the same instant as the event is not generated | Source zones differ by design; synthetic data avoids the open boundary questions | proposed |
| D-010 | 2026-11-19 | Synthetic rules: notice SLA = 5 business days (Mon-Fri, national holidays excluded) from trigger to service; certificates inclusive on both dates; certificate and notice boundary cases and state-holiday ambiguities are not generated | Keeps the synthetic ground truth unambiguous while the real rulings are open | proposed |
| D-011 | 2026-11-19 | A consent, or an identity verification, with exactly the same UTC instant as the message or call start is `cannot_determine`, not a pass or a gap. Without a transcript store, dues are taken to be disclosed at the call start in D4, and verification is read from D11 | Rule 1: ambiguity is never a claim; the tie question is still open above | proposed |
| D-012 | 2026-11-19 | Without ANTHROPIC_API_KEY the parser falls back to keyword matching on "Q<n>." questions (the LLM path in agent/parser is written but untested). Pass/fail stays in code either way. Findings are per event: one gap per breaching event, else one evidenced finding per account | Lets the pipeline run and be scored offline; D-007 is unchanged | proposed |
| D-013 | 2026-11-19 | Auditor workflow tables (V003): reviews, management comments and letter versions are append-only, the latest row wins, and findings are never touched. A disputed gap stays a gap in the register, summary and letter. A letter cannot be approved while `[To be completed by management]` placeholders remain. Reviewer names are self-declared (no login) | Rule 2 (never drop or soften a gap) must hold while auditors still record their judgement; attribution without an identity provider | proposed |
| D-014 | 2026-11-19 | A request can be an instruction instead of numbered questions ("run a compliance audit for accounts contacted in the previous month, sample size 300"). The platform then tests every guardrail in Rules & data (or only those named), grades them on a default scale Critical > Major > Minor (consent, hours, frequency, verification = Critical; notices, certification = Major; recordings = Minor) when the request gives none, and the auditor confirms this before the run. A period ("previous month", "last N days", "March 2026", "January to October 2026") is in India calendar days, start inclusive, end exclusive, relative to the day of the request; it limits the calls and messages tested, not notices. With no account list the sample is the stated number of accounts contacted in the period, chosen by a hash of account id and request reference so a re-run draws the same accounts | Auditors write requests in plain language; the sample and period must be explicit and repeatable | proposed |
