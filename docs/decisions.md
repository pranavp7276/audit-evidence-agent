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
