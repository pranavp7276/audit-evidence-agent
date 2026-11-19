# The CN book: tables, data, and which sandbox dataset each serves

Every team works on the same synthetic **CN book**: delinquent loan accounts across three fictional lenders (a bank, an NBFC and an MFI) with six months of
history (20 May to 17 November 2026): the platform keeps no activity older than six months (docs/decisions.md D-030). The tables keep **CN Core's names** (from the supplied CN_CORE and UAMDB DDL); the `book` schema gives the
sandbox's own field names for the datasets that remain as views.

The database holds only what an audit check, or a sandbox dataset the problem statement names, reads (docs/decisions.md D-029). Which evidence tag lives
in which column is in [evidence_coverage.md](evidence_coverage.md), generated from `config/source_map.yaml`.

Built by `db/migrations/V005`, `V009`, `V017` (pruning) and `V018` (evidence tags) and `python scripts/gen_book.py` (data). All data is synthetic.

## What is kept, and what was removed

| Dataset | Loaded (scale 0.1) | Table(s) | `book` view |
|---|---|---|---|
| D1 Account master | 10,000 | `cn_core.account`: id, lender, account number, customer, product, DPD, bucket, city | `book.d1_account_master` |
| D2 Borrower master | 8,500 | `cn_core.customer` (id, lender), `customer_contact_number` (number, type PRIMARY / ALTERNATE / REFERENCE, source, captured date), `customer_address` (type, city, state) | `book.d2_borrower_master` |
| D4 Contact history | about 345,000 events | `cn_core.tele_process_instance_call_logs` (+ the activity bridge and `tele_process_instance`) and `cn_core.communication_dashboard_t` | `book.d4_contact_history` |
| D5 Call transcripts | about 5,700 calls | `compliance.call_transcript_segment` (offsets, tags, language, ASR confidence) | `book.d5_call_transcripts` |
| D10 Consent and DND | 34,000 | `compliance.consent_dnd_registry` (borrower level) over `compliance.customer_consent` (events) | `book.d10_consent_dnd` |
| D11 Template registry | 400 | `cn_core.digital_template` (+ approval status, approved at, retired at) | `book.d11_template_registry` |
| D12 Policy library | 200 documents, 13 rules | `audit.kb_document` / `kb_clause` and `compliance.calling_policy_rule` (structured, per lender, effective-dated) | `book.d12_policy_library` |

Also kept, because a check reads them: `compliance.call_recording`, `call_session_xref`, `notice`, `holiday_calendar`, `collector_certification`,
`collector_status`, `registered_cli`, `dialer_config`, and `uamdb.users` / `organization` (collector, employee code, agency).

**Removed in V017:** D3 repayment history, D6 PTP ledger, D7 payment feed, D8 AA bank statements, D9 bureau snapshot and D13 channel cost (none bears on
a collections-conduct audit), and the tables behind them; borrower names, birth dates, e-mail addresses and address lines; branches, institutions,
lenders, collection cases, dispositions, the activity log, notice documents, tele campaigns and process types, roles and organisation types; every
column of a kept table that nothing read; the loose-file `raw` schema; and a stray test table.

The proposed full volumes are no longer a goal: `gen_book.py --scale 1.0` still scales the kept datasets.

## Retention: six months

Calls, recordings, transcripts, messages and notices older than six months are not kept. `python -m agent retention` shows what is older than the
horizon (today less six months) and removes it with `--apply` (needs `ALLOW_PURGE=1` on a shared database). Standing records that a result inside the
window can depend on are kept: consent events (a consent given before the window still covers a message inside it), certificates, collector status,
registered caller IDs, templates and the D12 rules. Audits, findings and their citation extracts are the audit's own records and are never purged.

An audit period that starts before the horizon is told so in three places: the confirm step, the plan in the agent's activity, and the letter's
assumptions. Anything that depends on records before the horizon is cannot determine, never compliant.

## The three lenders

| Lender (`institution_code`) | Type | Products | Calling hours (D12) | Daily attempts per contact number |
|---|---|---|---|---|
| Sahyadri Bank (`BANK01`) | Bank | Personal loan, business loan, credit card | 08:00 to 19:00; to **18:50 from 3 Aug 2026** | **4**; **5 from 1 Jul 2026** |
| Kaveri Finserv (`NBFC01`) | NBFC | Two-wheeler, consumer durable, business loan | 08:00 to 19:00 | 3 |
| Ganga Microfinance (`MFI01`) | MFI | Group and individual micro-loans | 09:00 to 18:00 | 2 |

D12 is per lender and effective-dated; each event is tested against the rule in force on its own date.

## Two dialers, on purpose

SlashRTC logs call times in IST with session ids like `SRTC-20260312-0001234`; CognifAI logs in UTC with `cgn-<uuid>`. `compliance.dialer_config` says
which zone and which clock (`clock_source`) each uses. A session is identified by dialer plus session id, has several status rows (for example CONNECTED
then DISPOSED) and counts once. About 2% of calls appear in both dialers; `compliance.call_session_xref` names the one that counts.

## Seeded problems

Late, withdrawn, wrong-purpose and missing consent (some late by only hours, a time-zone trap); calls after the lender's window closes; a contact number
called over the lender's cap, exactly at the cap (fine), and mirrored duplicates that would push a naive count over it; disclosure before identity
verification, no verification, failed verification, unclear transcript; recordings NOT_FOUND (a gap) or RETRIEVAL_FAILED (cannot determine); notices
dispatched or served late, never dispatched, never served; expired, lapsed and missing certificates; collectors with no employee code.
New with the evidence tags (V018): messages sent on pending, rejected or expired templates, or before a template was approved; calls by collectors after
they were terminated or while inactive; calls from a number that was never registered to the agency (a personal mobile) or registered only part-way
through the period; dues disclosed on calls to reference contacts. Transcripts exist for about 12% of accounts, so most other connected calls are honestly
"cannot determine" for identity verification. The audit request samples accounts that have transcripts, lists loan account numbers, and includes 3
that match nothing and some that match two loans.

## Ground truth

`gen_book.py` computes the true gaps with its own implementation of the rules over the generated rows, not through the platform:
`eval/gap_keys/CN-01.csv` (gaps) and `CN-01_cannot_determine.csv`. Score: `python -m eval.score --run <id> --gap-key eval/gap_keys/CN-01.csv`.
Request: `eval/requests/CN-01.txt` (eleven questions). The latest result is on the audit's Overview, under Acceptance criteria.

## Regenerating

```bash
python scripts/migrate.py            # structure (V005 to V018)
python scripts/migrate.py --staging  # views over the tables
ALLOW_RELOAD=1 python scripts/gen_book.py --scale 0.1   # replaces the book and clears earlier audit runs
python -m agent tags                                    # checks the evidence tags against the database
```

It refuses to run on a shared database without `ALLOW_RELOAD=1`. The knowledge base documents added by the generator carry the name `book-seed`;
a reload replaces those and leaves documents people added.
