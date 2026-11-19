# Contracts between modules

The source of truth is `agent/core/contracts.py`; this page explains it. Change both together.

## CheckSpec (parser → checks)
| Field | Meaning |
|---|---|
| `check_id` | Stable within a run, e.g. `Q3b` |
| `question_ref` | The request question it came from, e.g. `Q3`. Compound questions give several checks with one ref |
| `question_text` | The exact wording it was derived from |
| `check_type` | One of the types in `CheckType`; `other` if none fits (it is still reported, never dropped) |
| `sample` | How accounts are chosen: explicit list, or filter + period |
| `test` | What passes, in plain words plus parameters |
| `sources` | Systems the check reads |

## Finding (checks → store)
One per account per check, or per event (`subject_ref` = message id, call id, notice id) when the
check is event-level. Status is `evidenced`, `gap` or `cannot_determine`.
`evidenced` and `gap` need ≥ 1 Citation; `gap` needs a severity from the request's scale.
A check never returns nothing for a sampled account.

## Citation
`source_system`, `source_table` (raw.*), `record_key` (natural key or `_row_no`), the UTC timestamp
used, the original timestamp string, a minimal `extract`, and `role` (primary / supporting).

## Tools (agent → data)
Each tool in `agent/tools/` reads `staging.*` only, through the read-only role, and returns rows
that already include the citation fields. Signatures are in the stubs; owners fill the bodies
without changing the signatures unless agreed here.
