# Progress against docs/BUILD_PLAN.md

Updated at the end of each stage. The repository keeps its staging-view architecture (docs/architecture.md, D-028); the plan's `ledger.*` and `evidence.*` schemas are not built.

| Milestone | State | Where |
|---|---|---|
| M0 Profile | done | `config/source_map.yaml` + `python -m agent tags` -> `docs/evidence_coverage.md`; every mapped column is verified against the database |
| M1 Ledger | not built (staging views instead) | `db/staging/` |
| M2 P0 flags | done as checks | HRS-01, FRQ-01, CNS-01, CRT-01, REC-01, NOT-01 |
| M3 Transcript tags | VER-01 only | the other transcript tags are not captured (nothing in the data carries them) |
| M4 Agent | done | `agent/runtime/`, `agent/intake/` |
| M5 Pack + letter | done, with a claims check | `agent/services/pack.py`, `letter_lint.py` |
| M6 Eval | done on CN-01 | `eval/score.py` |
| M7 P1/P2 | 4 of the data-ready checks built | TPL-01, CLI-01, CNT-01, AGT-01 run; REC-03, FRQ-02, CRT-02/03, AGT-02, ACC-01, COV-01, NOT-02, DSP-01 and the transcript-tag checks are listed as not built or lacking tags in `docs/evidence_coverage.md` |

## Stage log

### 2026-11-20: evidence tags, new checks, pruning

- Added the catalog, tag spec, build plan and reference notes (`config/`, `docs/BUILD_PLAN.md`, `docs/reference/README.md`); decision D-028.
- V018 captures the tags that were missing and now feed a check: `clock_source`, template `approved_at` / `retired_at`, `compliance.collector_status`, `compliance.registered_cli`.
- Four checks added: TPL-01 (`template_approval`), AGT-01 (`collector_active`), CLI-01 (`caller_id_registered`), CNT-01 (`third_party_disclosure`), each with a tool, a guardrail and an independent oracle in `scripts/gen_book.py` (questions Q8 to Q11 of CN-01).
- V017 prunes the database to what an audit reads (D-029): six sandbox datasets, personal fields, unread columns, the `raw` schema. `tests/test_evidence.py` keeps it that way.
- A column removed by the pruning (`role_name`) was still cited by the certification check; it hid 13 gaps until the score caught it. `test_no_check_fails_to_run_on_real_data` now guards this.

Open questions (the catalog's `open_decisions`): OD-2 (attempts, not connects, are counted for the cap), OD-4 (a missing recording makes transcript checks cannot determine), OD-8 (an account with no events is cannot determine; `not_applicable` is not built).

