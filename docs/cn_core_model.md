# CN Core replica: tables, data and what is assumed

The platform audits against tables modelled on **CN_CORE** and **UAMDB** (from the supplied DDL exports and the telecalling
data model), loaded with synthetic but realistic collections data. Everything is created by `db/migrations/V005__cn_core_replica.sql`
and filled by `python scripts/gen_cn_core.py` (seeded; re-running replaces the data).

## Real structure (mirrors the supplied CN_CORE / UAMDB DDL)

Real table and column names, lower-cased; only the columns the audit needs. Oracle `NUMBER` is `bigint`/`numeric`, `VARCHAR2` is `text`,
`DATE`/`TIMESTAMP` is `date`/`timestamp`.

| Schema.table | Rows | What it holds |
|---|---|---|
| `uamdb.organization_type`, `organization`, `roles`, `users`, `user_role_link` | 3 / 7 / 5 / 136 / 136 | The lender, 4 tele-calling agencies and 2 field agencies; their users. `users.employee_code` is the collector id the certification register uses |
| `cn_core.customer`, `customer_contact_number` | 1,500 / 2,088 | Borrowers and their mobile numbers (primary and alternate) |
| `cn_core.account`, `account_customer_contact_number` | 1,800 / 2,512 | Loan accounts. `account_number` is what an auditor writes; `id` is the CN account id |
| `cn_core.collection_case` | 1,800 | One case per account with the allocated tele-call user and agency |
| `cn_core.disposition_group`, `disposition_code` | 3 / 5 | Disposition masters |
| `cn_core.tele_campaign`, `tele_process_type`, `tele_process_instance`, `tele_process_instance_user_link` | 4 / 8 / 80 / 120 | Calling campaigns (manual and campaign modes), monthly runs and the agents on them |
| `cn_core.tele_process_instance_call_logs` | 22,640 | One row per **call-status event**. A session has several rows (for example CONNECTED then DISPOSED) |
| `cn_core.tele_process_instance_activity` | 13,660 | Bridge: call session to account, customer and the activity it produced |
| `cn_core.activity_log` | 6,365 | The business outcome of each connected call (disposition, PTP) |
| `cn_core.communication_dashboard_t`, `digital_template` | 5,365 / 5 | The message log (WhatsApp, SMS) with recipient number; templates and their category |
| `cn_core.notice_document` | 1,146 | Notice documents |

## Added for the audit (not in the supplied DDL)

Marked `-- ext` in the migration: `dialer_code` on the process type, instance, call logs and the bridge (SlashRTC or CognifAI);
`template_id` on the message log.

## Not in CN Core as supplied: the `compliance` schema (our design, same style)

The supplied DDL has no consent, certification, policy-rule, holiday, recording or transcript tables. The audit needs them, so they live in
`compliance`. **If CN Core holds these elsewhere, map them in `db/staging/R__1*.sql` and nothing else changes.**

| Table | Rows | Purpose |
|---|---|---|
| `compliance.dialer_config` | 2 | Each dialer's name and the time zone of its call timestamps (SlashRTC IST, CognifAI UTC) |
| `compliance.call_session_xref` | 305 | Authoritative cross-reference for a call mirrored in both dialers, naming the canonical one |
| `compliance.calling_policy_rule` | 7 | **D12**, effective-dated: calling window start and end, daily attempts per contact number, notice dispatch and service limits |
| `compliance.holiday_calendar` | 14 | National and state holidays |
| `compliance.customer_consent` | 3,498 | Consent history per recipient number, channel and purpose (grant and revoke events) |
| `compliance.collector_certification` | 117 | Certificates keyed by employee code, with validity dates |
| `compliance.call_recording` | 6,365 | Recording store status per session: AVAILABLE, NOT_FOUND or RETRIEVAL_FAILED |
| `compliance.call_transcript_segment` | 19,991 | Transcript with tags and offsets into the recording (identity check, dues disclosure) |
| `compliance.notice` | 1,191 | Notice trigger, dispatch and service dates |

## How the platform reads it

`db/staging/R__1*.sql` builds typed views over these tables (UTC timestamps, original value and zone kept): `accounts`, `call_sessions`
(one row per dialer-qualified session, with `statuses`, `connected`, `counts_as_attempt`, `is_mirror_duplicate`), `messages`, `consents`,
`recordings`, `transcript_segments`, `policy_rules`, `holidays`, `notices`, `collectors`, `certifications`, `dialers`. The agent's tools read
only these views through the read-only role.

Joins worth knowing: a call session is `(dialer_code, call_session_id)`; the collector is `call_user_id` → `users.user_id` →
`users.employee_code` → certification register; a message's purpose is `communication_dashboard_t.template_id` → `digital_template.sms_category`;
consent is matched on the recipient **number** and channel, not the account.

## Seeded problems (and why they are there)

Late consent (some by hours, a time-zone trap), consent withdrawn later, wrong-purpose consent (a collections consent does not cover a promotional
message), no consent at all; calls after the window closes (18:51 to 18:59 is a gap only from 1 April, when the window end moved from 19:00 to 18:50);
a contact number called over the cap (4 until 31 May, 5 from 1 June), exactly at the cap (fine) and mirrored duplicates that would push a naive count over
the cap; disclosure before identity verification, no verification, failed verification, unclear transcript; recordings NOT_FOUND (a gap) or
RETRIEVAL_FAILED (cannot determine); notices dispatched or served late, never dispatched, never served; expired, lapsed and missing certificates, and
collectors with no employee code (cannot determine). The request lists loan account numbers, including 3 that match nothing and some that match two
loans (the same number under two institutions).

## Ground truth

`gen_cn_core.py` computes the true gaps with its own independent implementation of the rules, over the generated rows, not through the platform:
`eval/gap_keys/CN-01.csv` (gaps) and `CN-01_cannot_determine.csv`. Score a run: `python -m eval.score --run <id> --gap-key eval/gap_keys/CN-01.csv`.
Request: `eval/requests/CN-01.txt`. Current result on this data: 322 of 322 true gaps found, no false gaps, no unsupported claims.

## Regenerating

```bash
python scripts/migrate.py            # V005 creates the tables
python scripts/migrate.py --staging  # views
python scripts/gen_cn_core.py        # data (truncates and reloads the CN Core replica tables)
```
