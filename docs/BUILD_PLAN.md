# Build plan: evidence flags + audit evidence pack agent

**For:** Claude Code (VS Code), working in the team's shared repo with Postgres.
**Owner:** Pranav (Product). **Status:** ready to build, M0 first.

> How this repository relates to the plan: the platform already runs end to end on a staging-view architecture (docs/architecture.md), which
> serves the same purpose as the plan's `ledger.*` and `evidence.*` schemas. The check ids, flag and tag codes, reason wording and the rules in
> sections 2 and 4 are adopted as written. Progress against the milestones is in `PROGRESS.md`, and the decision is D-028 in `docs/decisions.md`.

---

## How to use this plan (instructions to Claude Code)

1. Read these files in this order before writing any code:
   - `docs/BUILD_PLAN.md` (this file)
   - `config/check_catalog.yaml`: 29 checks (IDs like `HRS-01`). This is the single source of truth for what is tested.
   - `config/evidence_tags.yaml`: fields, flags and transcript tags per activity (call, field visit, message, notice, payment) and per master record.
   - `docs/reference/README.md`: where the rules come from (4 real lender/agency documents in `docs/reference/sources/`).
2. Build milestone by milestone (section 10). At the end of each milestone: run the tests, update `PROGRESS.md` (what was built, how to run it, open questions), commit, then stop and summarise for the team.
3. **Never guess column names.** M0 profiles the datasets and writes `config/source_map.yaml`. Every later step reads column names from that file.
4. If the repo already has a language or framework set up, follow it. Otherwise use Python 3.11, Postgres, SQLAlchemy/psycopg, pydantic, pytest, and the Anthropic SDK for LLM steps (model name in config).
5. If a rule or threshold is unclear, check `open_decisions` in the catalog. Use the suggested default, mark it with `# OD-n` in code, and list it in `PROGRESS.md`. Don't silently pick something else.

---

## 1. Goal in one paragraph

Every activity the collections platform logs (call, field visit, WhatsApp/SMS/email, notice, payment) carries **tags**: the raw facts an auditor needs, such as consent ID used, recording status, caller ID and contact source. It also carries **flags**: Y/N/U answers per compliance check, each with the record IDs that prove it. When an audit request arrives, the agent splits it into checks, pulls the flags and raw records for the sampled accounts, re-verifies them, and writes an evidence pack, a gap report and a draft letter. Every statement cites a record. The target is a 300-account, 10-question request in under 2 hours, with gap recall ≥ 95%, false gaps < 5%, and zero compliance claims without evidence.

---

## 2. Non-negotiable rules (enforce in code and tests)

| # | Rule | How it is enforced |
|---|---|---|
| G1 | No `evidenced` verdict without ≥ 1 cited record | DB check constraint + pack linter fails the build |
| G2 | Gaps are never dropped or softened | Letter generator can't filter gaps; test compares gap count in letter vs gap report |
| G3 | Unknown ≠ compliant | Three-valued flags `Y / N / U`. Missing source, unknown timezone or missing transcript → `U` → `cannot_determine` |
| G4 | Agency claims aren't evidence | Status/remarks supplied by an agency (e.g. "dialer blocks calls after 7 PM", "NA – no field") are tested against data, never copied as verdicts |
| G5 | Rule parameters come from D12 | Hours, caps and notice days are read from D12 and versioned (`rule_version`). Catalog `defaults` are fallback only |
| G6 | Timestamps normalised to IST before any hour/day/date test | One `tz` module; every source has a declared or inferred tz (M1) |
| G7 | Limits are per borrower per IST day | Aggregate across all numbers, accounts and channels of the borrower |
| G8 | Minimal PII in the pack | Account ref, dates, record IDs, last-4 of numbers. No names or full numbers unless the request asks |
| G9 | Flags record, they don't block | Pre-dispatch prevention is out of scope (CO-02). A breach is logged, flagged `N` and reported |
| G10 | Append-only evidence | Flags and verdicts are never updated in place. Re-runs write new rows with `run_id` |

---

## 3. Architecture

```
 sources (D4 D5 D10 D11 D12, dispatch history, holiday calendar,
          collector roster + cert register, recordings, transcripts)
        │  adapters (one per source; read config/source_map.yaml)
        ▼
 ledger.*   canonical activity ledger: event envelope + call / field_visit /
            message / notice / payment, effective-dated masters (SCD-2)
        │  flag engine (deterministic rules per check_id, params from D12 @ rule_version)
        │  transcript tagger (LLM -> JSON, verbatim-quote validated)
        ▼
 evidence.* flag rows (Y/N/U + reason_code + evidence_refs), transcript_tag rows
        │
        ▼
 agent      parse request -> triage -> check plan -> call tools -> re-verify ->
            verdict per account x check -> severity grade
        │
        ▼
 pack       index.xlsx, extracts/, gap_report.xlsx, response_letter.docx, run_manifest.json
```

**Why precompute flags:** precomputed flags keep a 300 × 10 request inside 2 hours. The agent's job is judgement: which checks a question means, where to look, whether the evidence proves the point. Row-by-row arithmetic is done in advance.

**Why the agent re-verifies:** a stored flag is an index, not proof. For each sampled account × check, the agent re-derives the verdict from raw ledger fields. If the stored flag and the raw fields disagree, that becomes a `DATA_CONFLICT` finding in the pack.

---

## 4. What gets tagged and flagged, by activity

The full spec is in `config/evidence_tags.yaml`. This is the summary.

| Activity | Key tags (raw facts to keep) | Flags (→ check IDs) |
|---|---|---|
| **Call** (tele + FOS phone) | call_id, lead_id, contact_source (borrower / alternate / reference), cli_number, call_origin, attempt/answer/end ts + source_tz, call_status, disposition, recording_id + recording_status + duration, transcript_id | F_IN_HOURS (HRS-01), F_BORROWER_DAY_SEQ / F_OVER_DAILY_CAP (FRQ-01), F_RECORDING_PRESENT / COMPLETE (REC-01/03), F_COLLECTOR_CERTIFIED (CRT-01), F_COLLECTOR_ACTIVE (AGT-01), F_REGISTERED_CLI (CLI-01), F_NON_FIRST_PARTY (CNT-01), F_DISPOSED (DSP-01) |
| **Call transcript** | turn index + offset for each tag | T_RECORDING_DISCLAIMER (REC-02), T_SELF_INTRO / T_LENDER_NAMED (IDN-01), T_RPC_CONFIRMED + T_DUES_DISCLOSED → T_DISCLOSED_BEFORE_RPC (VER-01), T_THIRD_PARTY_DISCLOSURE, T_ABUSE_THREAT (CND-01), T_FALSE_PROMISE (CND-02), T_PERSONAL_PAYMENT_ASK (CND-03), T_SENSITIVE_OCCASION (CND-04), T_DISPOSITION_MISMATCH (DSP-01), T_CUSTOMER_NO_CALL_REQUEST (FRQ-02) |
| **Field visit** | visit_id, server-stamped check-in/out, geo + accuracy, address visited, person met, outcome, photo, receipt | F_IN_HOURS (HRS-01), F_GEO_VERIFIED (VIS-01), F_OUTCOME_CAPTURED_SAME_DAY (VIS-02), F_COLLECTOR_CERTIFIED / ACTIVE, F_THIRD_PARTY_MET (CNT-01), F_AGENCY_NOTICE_BEFORE (NOT-02) |
| **Message** (WhatsApp / SMS / email) | message_id, channel, template_id + version, sender_id, sent/delivered ts + source_tz, consent_id_at_send, content_hash | F_CONSENT_VALID_AT_SEND (CNS-01), F_TEMPLATE_APPROVED_AT_SEND (TPL-01), F_REGISTERED_SENDER (CLI-01), F_IN_HOURS only if D12 says so |
| **Notice** | notice_id, type, trigger date, due_by (holiday-aware, borrower's state), dispatch ts, mode, tracking ref, **service date**, POD document | F_DISPATCHED_ON_TIME, F_SERVED_ON_TIME, F_POD_PRESENT, F_HOLIDAY_ADJUSTED (NOT-01), agency-appointment notice (NOT-02) |
| **Payment** | receipt_id, mode, beneficiary account, collected_by, collected ts, deposit slip + ts | F_RECEIPT_ISSUED, F_DEPOSITED_WITHIN_TAT (PAY-01), F_AUTHORISED_CHANNEL (CND-03) |
| **Collector master** (SCD-2) | status history, DRA cert no + validity, police verification / RCU, training, portfolio assignments, registered CLIs | feeds CRT-01/02/03, AGT-01/02, ACC-01, CLI-01 |
| **Contact & consent master** | contact source/relation, consent (channel, purpose, captured_at, revoked_at, artefact), preferences, geocoded addresses + state | feeds CNS-01, CNT-01, FRQ-02, VIS-01, NOT-01 |
| **Allocation** (SCD-2) | account → agency → TL → collector, valid_from/to | feeds COV-01, NOT-02, AGT-02 |

**An agency "NA – no field" claim** is evidenced by zero `field_visit` rows for that agency in the period. The zero-row query is cited by its query hash and run_id.

---

## 5. Data model (Postgres)

Schemas: `raw` (as loaded), `ledger` (canonical), `evidence` (flags, tags, verdicts), `audit` (requests, runs, packs).

```sql
-- envelope shared by all activity tables (one row per event)
ledger.event(
  event_id text pk, event_type text check (event_type in ('call','field_visit','message','notice','payment')),
  lender_code text, account_id text, borrower_id text, agency_id text, collector_id text,
  event_ts_utc timestamptz, source_tz text, clock_source text, tz_resolution text,  -- declared|inferred|unknown
  event_date_ist date generated always as ((event_ts_utc at time zone 'Asia/Kolkata')::date) stored,
  dpd_at_event int, source_system text, source_pk text, rule_version text,
  created_at timestamptz default now(), corrects_id text null)

ledger.call(event_id pk/fk, call_id, lead_id, contact_number_hash, contact_last4, contact_source, contact_relation,
            cli_number, call_origin, answer_ts_utc, end_ts_utc, ring_time_s, talk_time_s, call_status,
            disposition, sub_disposition, ptp_amount, ptp_date, recording_id, recording_status,
            recording_duration_s, transcript_id)
ledger.field_visit(...), ledger.message(...), ledger.notice(...), ledger.payment(...)   -- fields per evidence_tags.yaml

-- effective-dated masters
ledger.collector_status(collector_id, status, valid_from, valid_to, source_pk)
ledger.collector_cert(collector_id, cert_type, cert_no, valid_from, valid_to, source_pk)
ledger.consent(consent_id, borrower_id, channel, purpose, captured_at_utc, source_tz, method, artefact_id, revoked_at_utc)
ledger.contact(borrower_id, number_hash, last4, source, relation, added_at, valid_to)
ledger.preference(...), ledger.allocation(...), ledger.template(template_id, version, approved_at, retired_at)
ledger.holiday(date, scope, state_code), ledger.rule_param(rule_version, key, value, valid_from, source_pk)  -- from D12

-- flags: one row per (event or subject) x flag x run
evidence.flag(
  flag_row_id bigserial pk, run_id text, check_id text, flag_code text,
  subject_type text, subject_id text, account_id text, borrower_id text, collector_id text, event_date_ist date,
  value text check (value in ('Y','N','U')), reason_code text,
  params jsonb,           -- the exact D12 params used, e.g. {"window":"08:00-19:00","rule_version":"D12@v3"}
  evidence_refs jsonb not null,  -- [{"source":"consent_registry","table":"...","pk":"C-123","field":"captured_at","value":"..."}]
  engine_version text, computed_at timestamptz default now(),
  constraint g1 check (value <> 'Y' or jsonb_array_length(evidence_refs) > 0))

evidence.transcript_tag(run_id, call_id, tag_code, value, turn_idx, offset_s, quote, model, prompt_version, validated bool)

-- request-level outputs
audit.request(request_id, source_file, received_at, period_from, period_to, severity_scale jsonb, parsed jsonb)
audit.check_plan(request_id, question_no, question_text, triage, check_ids text[], sample_def jsonb, test_def jsonb, approved_by)
audit.verdict(run_id, request_id, question_no, account_id, check_id,
              verdict text check (verdict in ('evidenced','gap','cannot_determine','not_applicable')),
              reason_codes text[], severity text, flag_row_ids bigint[], citations jsonb not null,
              constraint g1v check (verdict <> 'evidenced' or jsonb_array_length(citations) > 0))
```

---

## 6. Flag engine

- **Rule registry:** one module per check family (`hrs.py`, `frq.py`, `cns.py`, ...). Each rule is registered by `check_id` and declares `applies_to` and `engine` from the catalog. A startup test fails if any catalog check with `engine: deterministic | hybrid` has no rule.
- **Signature:** `evaluate(subject, ctx) -> FlagResult(value: Y|N|U, reason_code, evidence_refs, params)`. `ctx` carries the D12 params at the correct `rule_version`, the tz resolver, the holiday calendar and master lookups as of the event date.
- **Timezone module:**
  1. Read the declared tz per source from `source_map.yaml`.
  2. If a source has no declared tz, **infer** it by joining the same events across sources (e.g. the same call_id in the dialer log and the CRM) and taking the modal offset. Store `tz_resolution = inferred` and save the evidence for the inference.
  3. If it still can't be resolved, use `U` with `TZ_UNRESOLVED`. Never assume.
- **Borrower-day aggregation:** a window function over `ledger.event` partitioned by `borrower_id, event_date_ist`, ordered by ts. FRQ-01 counts either attempts or connects depending on OD-2.
- **Notice clock:** `due_by = trigger_date + N` days. N and working-vs-calendar days come from D12/request; holidays come from the borrower's state plus national holidays. Store the holiday calendar version in `params`.
- **Reason codes:** an enum, so the gap report and the scoring can group on it:

```
HRS:  OUTSIDE_WINDOW_EARLY, OUTSIDE_WINDOW_LATE, TZ_UNRESOLVED
FRQ:  CAP_EXCEEDED, DPD_UNKNOWN
CNS:  CONSENT_MISSING, CONSENT_AFTER_MESSAGE, CONSENT_REVOKED, CONSENT_CHANNEL_MISMATCH
TPL:  TEMPLATE_UNKNOWN, TEMPLATE_NOT_APPROVED_AT_SEND, TEMPLATE_RETIRED
CLI:  CLI_UNREGISTERED, MANUAL_DIAL
REC:  RECORDING_MISSING, RECORDING_TRUNCATED, MONTH_WITHOUT_RECORDINGS
VER:  DUES_BEFORE_RPC, NO_RPC, THIRD_PARTY_DISCLOSURE, NO_TRANSCRIPT
CND:  ABUSE_THREAT, FALSE_PROMISE, PERSONAL_PAYMENT_ASK, SENSITIVE_OCCASION
CRT:  CERT_EXPIRED, CERT_NOT_YET_VALID, CERT_NOT_FOUND
AGT:  COLLECTOR_INACTIVE, COLLECTOR_TERMINATED, COLLECTOR_UNKNOWN, SHARED_ACROSS_LENDERS
NOT:  DISPATCH_LATE, SERVICE_LATE, SERVICE_DATE_MISSING, POD_MISSING
VIS:  NO_GEO, GEO_TOO_FAR, OUTCOME_MISSING, OUTCOME_BACKFILLED
PAY:  NO_RECEIPT, DEPOSIT_MISSING, DEPOSIT_LATE, UNAUTHORISED_CHANNEL
ANY:  SOURCE_MISSING, DATA_CONFLICT
```

---

## 7. Transcript tagger (LLM)

- Run it only on calls the request needs: sampled accounts, in the period, and only where a transcript check is in the plan. Cache results by `(call_id, prompt_version, model)`.
- Output is strict JSON matching a pydantic schema: `{tag_code, value: Y|N|U, turn_idx, offset_s, quote}`.
- **Quote validation:** `quote` must be a verbatim substring of the transcript at `turn_idx`. If it isn't, the tag becomes `U` with `validated=false`. This blocks hallucinated evidence.
- VER-01 is **hybrid**: the LLM only locates `T_RPC_CONFIRMED` and `T_DUES_DISCLOSED` turns; code compares the turn indices.
- If there is no transcript or recording for a call, every transcript tag for that call is `U` (OD-4). REC-01 separately records the missing recording as a gap.
- Use the QM scorecard wording (`qm_parameters` in the catalog) in the prompts. It is the lender's own definition, e.g. right party confirmed by prefix + last name.
- Concurrency: async batch with a rate limit. Budget the time so tagging fits within the 2-hour run.

---

## 8. Agent workflow and tools

**Tools the agent must call** (required by the problem statement; expose each as a named tool over the ledger and evidence schemas):

| Tool | Backs onto | Used by checks |
|---|---|---|
| `warehouse_sql(query)` (read-only, row-limited, logged with query hash) | all schemas | DPD, allocation, addresses, any ad-hoc |
| `contact_log(account_ids, period, types)` | ledger.event + call/visit/message | HRS, FRQ, CLI, CNT, DSP, COV, VIS |
| `transcript_recording_store(call_ids)` | ledger.call + transcript_tag | REC, VER, IDN, CND |
| `consent_registry(borrower_ids, channel)` | ledger.consent | CNS |
| `template_registry(template_ids)` | ledger.template | TPL |
| `dispatch_tracker(account_ids, notice_types)` | ledger.notice + holiday | NOT |
| `certification_register(collector_ids, dates)` | collector_cert + collector_status | CRT, AGT, ACC |

**Steps**

1. **Parse** the request (PDF or email text) into questions, sample (account list or rule), period, and severity scale. Save to `audit.request`.
2. **Triage** each question as `account_check`, `vendor_document` or `not_testable`, using the catalog sections `checks`, `vendor_document_requests` and `not_testable_from_systems`. Compound questions become several check IDs.
3. **Check plan:** write `audit.check_plan` and a readable `check_plan.md` (question → check IDs → sources → test → sample). Pause for human approval only if `--review` is passed; the default is autonomous so the run fits the time limit.
4. **Execute:** for each account × check, call the tools, read the flags, and re-derive the verdict from raw fields. Aggregate event-level results to account level:
   - any `N` → **gap** (list every offending event)
   - all `Y` → **evidenced** (cite every event)
   - otherwise any `U` → **cannot_determine**
   - no in-scope events → **not_applicable**, citing the zero-row query (OD-8)
5. **Grade** each gap on the request's own severity scale. Map reason_code → scale level with a table that is reviewed once per request and saved in the run. Fallbacks: catalog `severity_hint`, then the MVA 100-point weights.
6. **Build the pack** (section 9) and run the linter.

Questions classed as `vendor_document` go into the letter under "Documents to be provided by the agency", with the verdict `cannot_determine`.

---

## 9. Evidence pack output

```
packs/<request_id>/<run_id>/
  index.xlsx            one row per (question, account, check): verdict, severity, reason_codes, citation IDs [E-000123]
  gap_report.xlsx       gaps only, grouped by question → severity → reason_code; counts + account list
  extracts/E-000123.json   the cited record(s): source, table, pk, fields used, values, tz-normalised ts
  extracts/transcripts/<call_id>.txt   only the quoted turns (+/- 1 turn), not full transcripts
  check_plan.md         how each question was interpreted
  response_letter.docx  draft for compliance review
  run_manifest.json     run_id, rule_version, source snapshot hashes, model + prompt versions, timings
```

**Response letter:** one section per question. Each section gives the interpretation, then counts (evidenced / gap / cannot determine / not applicable), then the gaps stated plainly with severity, then the documents the agency must supply. Every factual sentence carries `[E-…]` citations. Use Compliant / Gap / Cannot determine wording, never bare Yes/No.

**Pack linter** (runs in CI and at the end of every run):
- every `evidenced` row has ≥ 1 citation, and every citation file exists
- the gap count in the letter equals the gap count in gap_report, per question
- no PII beyond the allowed fields (regex check on names and 10-digit numbers)
- every `[E-…]` in the letter resolves in the index

---

## 10. Milestones

| M | Deliverable | Done when |
|---|---|---|
| **M0** Profile | `scripts/profile_sources.py` → `docs/data_profile.md` (tables, columns, row counts, null %, sample values, candidate keys, timestamp columns + suspected tz) and `config/source_map.yaml` mapping logical sources (contact_log, consent_registry, …) to real D-tables/columns. List which `evidence_tags.yaml` fields exist in the data and which are missing | Pranav reviews source_map; missing fields listed |
| **M1** Ledger | Postgres DDL + adapters load all sources into `ledger.*`; tz resolver with inference report; masters as SCD-2 | Row counts reconcile to raw; tz report shows every source resolved or flagged |
| **M2** Flags P0 | Deterministic rules for HRS-01, FRQ-01, CNS-01, CRT-01, REC-01, NOT-01 (the problem statement's named checks) | Unit tests per reason_code using seeded edge cases (late consent, tz shift, expired cert, missing recording, late service on a holiday) |
| **M3** Transcript tags | VER-01 (hybrid), REC-02, IDN-01, CND-01/02 with quote validation | A hand-labelled set of 30 calls reaches ≥ 95% agreement; zero unvalidated quotes reach a verdict |
| **M4** Agent | Request parser, triage, check plan, tool layer, verdict aggregation | All 3 public requests produce a check plan a human agrees with |
| **M5** Pack + letter | Section 9 outputs + linter | Linter passes on all 3 public requests |
| **M6** Eval | `scripts/eval.py` scores against the public gap keys: recall, false-gap rate, unsupported-claim count, wall-clock; confusion broken down by check_id and reason_code | Recall ≥ 95%, false gaps < 5%, unsupported claims = 0, 300×10 < 2 h |
| **M7** P1/P2 flags | TPL-01, CLI-01, CNT-01, AGT-01/02, DSP-01, CND-03/04, VIS-01/02, PAY-01, COV-01, ACC-01, REC-03, NOT-02, CRT-02/03, FRQ-02 (each one is built only if M0 found the data) | Each check either runs or is listed as `cannot_determine: data not available` |

**Eval discipline:** never tune prompts or rules against the hidden requests. When a public request misses a gap, add a regression test named after its reason_code.

---

## 11. Beyond the hackathon: the CN product backlog

`evidence_tags.yaml` marks each field's status in CN as `known / likely / gap / new`, from current knowledge. **Confirm it against CN_CORE and UAMDB.** The items that most need building in CN so that evidence exists at source:

1. `source_tz` + `clock_source` on every event. Prefer server or dialer clocks over browser clocks; the platform has already seen browser-vs-server timer mismatches.
2. A granular `call_status`: unreachable vs no-answer vs cut-while-ringing vs connected. Without it, attempts can't be told apart from connects for caps.
3. `recording_status` + duration, to catch missing or truncated recordings.
4. `contact_source` / `relation` on every number (borrower vs alternate vs reference).
5. `consent_id_at_send` + `content_hash` on every message.
6. On notices: `trigger_date`, a holiday-aware `due_by`, and `service_date` + POD from vendor feeds.
7. Collector **status history** (not overwritten), plus DRA validity, police verification and training dates.
8. On field collections: deposit slip + TAT and beneficiary account.
9. Effective-dated allocation history.
10. A versioned rule-config table (D12-equivalent), so a flag can say which rule it was judged against.

---

## 12. Open decisions

These are in the catalog as `OD-1…OD-7`, plus one more:

- **OD-8:** an account with no in-scope events (e.g. no WhatsApp messages in the period). Suggestion: verdict `not_applicable`, cite the zero-row query, report it in its own column and score it as non-gap. Confirm against the public gap keys in M6.

Use the suggested defaults until the team decides, and mark them in code with `# OD-n`.
