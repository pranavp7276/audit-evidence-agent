# The sandbox book: tables, data, and how it maps to D1 to D13

Every team works on the same synthetic **CN book**: delinquent loan accounts across three fictional lenders (a bank, an NBFC and an MFI) with
12 months of history (November 2025 to October 2026). The tables keep **CN Core's names** (from the supplied CN_CORE and UAMDB DDL); the
`book` schema gives the sandbox's own field names for D1 to D13 as views, so nothing is renamed.

Built by `db/migrations/V005` and `V009` (structure) and `python scripts/gen_book.py` (data). All data is synthetic.

## Volumes: proposed versus loaded

`gen_book.py --scale 1.0` produces the proposed volumes; the default `--scale 0.1` keeps every ratio at one tenth and is what is loaded
(about 290 MB, which is why: full scale would be about 2.9 GB and needs a database sized for roughly 6 million rows).

| Dataset | Proposed (scale 1.0) | Loaded (scale 0.1) | Table(s), CN Core names | `book` view |
|---|---|---|---|---|
| D1 Account master | 100,000 accounts | 10,000 | `cn_core.account` (+ city, restructure/settlement/legal flags) | `book.d1_account_master` |
| D2 Borrower master | 85,000 | 8,500 | `cn_core.customer`, `customer_contact_number` (+ source, captured date), `customer_email`, `customer_address`, `customer_name_variant` | `book.d2_borrower_master` |
| D3 Repayment history | 1.2M rows | 120,000 | `cn_core.account_payment_schedule` (+ amount paid, paid date, mode, bounce reason) | `book.d3_repayment_history` |
| D4 Contact history | 3M attempts | about 266,000 | `cn_core.tele_process_instance_call_logs` (+ the activity bridge) and `cn_core.communication_dashboard_t` | `book.d4_contact_history` |
| D5 Call transcripts | 60,000 calls | about 5,700 calls (29,000 turns) | `compliance.call_transcript_segment` (+ language, ASR confidence, offsets) | `book.d5_call_transcripts` |
| D6 PTP ledger | 150,000 | 27,480 | `cn_core.ptp_ledger` | `book.d6_ptp_ledger` |
| D7 Payment feed | 400,000 | 40,000 | `cn_core.payment_feed` | `book.d7_payment_feed` |
| D8 AA bank statements | 20,000 borrowers x 12 months | 1,700 borrowers (192,000 rows) | `cn_core.aa_bank_statement` | `book.d8_bank_statements` |
| D9 Bureau snapshot | 85,000 borrowers, monthly | 8,500 x 12 (102,000) | `cn_core.bureau_snapshot`, `bureau_tradeline` | `book.d9_bureau_snapshot` |
| D10 Consent and DND | 85,000 | 8,500 x 4 channels (34,000) | `compliance.consent_dnd_registry` (borrower level) over `compliance.customer_consent` (events) | `book.d10_consent_dnd` |
| D11 Template registry | 400 | 400 | `cn_core.digital_template` (+ language, approval status) | `book.d11_template_registry` |
| D12 Policy library | about 200 documents | 200 | `audit.kb_document` / `kb_clause` (the Knowledge base) and `compliance.calling_policy_rule` (structured, per lender) | `book.d12_policy_library` |
| D13 Channel cost and capacity | per channel and agency | 76 rows | `cn_core.channel_cost_capacity` | `book.d13_channel_cost` |

Not in the sandbox list but needed for CO-04: notices (`compliance.notice`), the holiday calendar, the collector roster (`uamdb.users`,
`organization`, `roles`) and the certification register (`compliance.collector_certification`, keyed by employee code).

## The three lenders

| Lender (`institution_code`) | Type | Products | Calling hours (D12) | Daily attempts per contact number |
|---|---|---|---|---|
| Sahyadri Bank (`BANK01`) | Bank | Personal loan, business loan, credit card | 08:00 to 19:00; to **18:50 from 1 Apr 2026** | **4**; **5 from 1 Jun 2026** |
| Kaveri Finserv (`NBFC01`) | NBFC | Two-wheeler, consumer durable, business loan | 08:00 to 19:00 | 3 |
| Ganga Microfinance (`MFI01`) | MFI | Group and individual micro-loans | 09:00 to 18:00 | 2 |

Notice limits are the same for all lenders (dispatch within 3 business days, service within 7). The 200 policy documents include each lender's
calling-hours and contact-frequency policies (with their dated versions) stating exactly these numbers, plus regulator circulars with the outer limits.

## Real CN Core structure versus what we added

Real tables and columns (from the supplied DDL): `uamdb.*`, `cn_core.customer`, `account`, `collection_case`, `customer_contact_number`,
`account_customer_contact_number`, `customer_address`, `customer_email`, `branch`, `institution`, `lender`, `account_payment_schedule`,
`tele_process_type`, `tele_process_instance`, `tele_process_instance_call_logs`, `tele_process_instance_activity`, `activity_log`,
`communication_dashboard_t`, `digital_template`, `notice_document`. Columns marked `-- ext` in the migrations are additions (for example
`dialer_code`, the paid columns on the payment schedule). Wholly new tables: `ptp_ledger`, `payment_feed`, `aa_bank_statement`,
`bureau_snapshot`, `bureau_tradeline`, `channel_cost_capacity`, `customer_name_variant`, and the whole `compliance` schema (the supplied DDL has none of it).

## Two dialers, on purpose

SlashRTC logs call times in IST with session ids like `SRTC-20260312-0001234`; CognifAI logs in UTC with `cgn-<uuid>`. A session is identified by
dialer plus session id, has several status rows (for example CONNECTED then DISPOSED) and counts once. About 2% of calls appear in both dialers;
`compliance.call_session_xref` names the one that counts.

## Seeded problems

Late, withdrawn, wrong-purpose and missing consent (some late by only hours, a time-zone trap); calls after the lender's window closes (a call at
18:55 is a gap for the bank from 1 April and fine before); a contact number called over the lender's cap, exactly at the cap (fine), and mirrored
duplicates that would push a naive count over it; disclosure before identity verification, no verification, failed verification, unclear transcript;
recordings NOT_FOUND (a gap) or RETRIEVAL_FAILED (cannot determine); notices dispatched or served late, never dispatched, never served; expired,
lapsed and missing certificates; collectors with no employee code. Transcripts exist for about 12% of accounts (the proposal's 60,000 of roughly
600,000 connected calls), so most other connected calls are honestly "cannot determine" for identity verification. The audit request samples accounts
that have transcripts, lists loan account numbers, and includes 3 that match nothing and some that match two loans.

## Ground truth

`gen_book.py` computes the true gaps with its own implementation of the rules over the generated rows, not through the platform:
`eval/gap_keys/CN-01.csv` (gaps) and `CN-01_cannot_determine.csv`. Score: `python -m eval.score --run <id> --gap-key eval/gap_keys/CN-01.csv`.
Request: `eval/requests/CN-01.txt`. Current result: **427 of 427 true gaps found, no false gaps, no unsupported claims**.

## Regenerating

```bash
python scripts/migrate.py            # structure (V005, V009, V010)
python scripts/migrate.py --staging  # views over the tables
ALLOW_RELOAD=1 python scripts/gen_book.py --scale 0.1   # replaces the book and clears earlier audit runs
```
It refuses to run on a shared database without `ALLOW_RELOAD=1`. The knowledge base documents added by the generator carry the name `book-seed`;
a reload replaces those and leaves documents people added.
