# Audit evidence pack agent

Answers a lender or regulator audit request on outsourced collections with a complete evidence
pack, a gap report graded on the request's severity scale, and a draft response letter, where
every statement traces to a source record. Brief: [docs/problem.md](docs/problem.md).

## Quick start (about 10 minutes)
Needs Docker, Python 3.11+, make (Windows: use WSL).

```bash
git clone <repo-url> && cd audit-evidence-agent
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
make install
# copy the data files from the shared drive into data/raw/ (paths in data/manifest.yaml)
make data-check      # confirms you have the same data as everyone else
make setup           # starts Postgres, applies migrations, loads raw, builds staging
make test
```

## The platform (for collections auditors)
```bash
python -m agent serve                                          # http://127.0.0.1:8000
python -m agent serve --host 0.0.0.0                           # let coworkers on your network connect
APP_PASSWORD=choose-one python -m agent serve --host 0.0.0.0   # require a password (any user name)
```
New users and team members: open **Guide** in the left menu (how to run an audit, review results, work with the data, set up a machine).
The data is a CN Core replica (docs/cn_core_model.md). The auditor's workflow, start to finish:
1. **New audit request:** upload or paste the request (PDF, `.eml`, text), either numbered questions or a plain
   instruction such as *"Run a compliance audit for all accounts contacted in the previous month, sample size 300"*
   (every guardrail is tested, the period is read, and 300 accounts are drawn from those contacted in it). The platform shows how each question
   was read; confirm or change the test, set severities from the request's scale, split bundled questions.
   Sampled accounts with no records are flagged before anything runs.
2. **Summary:** verdict, gaps by severity, where gaps concentrate (collectors, months), and a next-steps checklist.
3. **Questions:** how each question was tested and its result; write the management comment for each.
4. **Gap register and Follow-up:** every gap with the records it cites. Confirm, dispute (with a reason), plan
   remediation, singly or in bulk. Items that could not be determined are chased here. A dispute adds a note;
   the gap is still reported (CLAUDE.md rule 2).
5. **Accounts:** one borrower's file with every record on a UTC timeline, events behind findings highlighted.
6. **Response letter:** generated from the findings and your comments, edited, versioned and taken through
   draft, compliance review and approved (approval is blocked while placeholders remain).
7. **Evidence pack:** zip with index, extracts, gap report, follow-up list, review trail, letter, rules.
8. **Knowledge base and Guardrails:** upload a circular, policy or SOP; it is split into clauses and draft guardrails are suggested from
   them. Compliance reviews and publishes each guardrail with a default severity and a priority weight (1 to 3, with a recorded reason above 1).
   Weights only order the review queue (severity first, then weight); they never decide or hide a gap. Guardrails are versioned and each audit
   records the version it applied.
9. **Rules & data:** the D12 limits in force, what each check tests, the assumptions, and the data read.

Findings are never edited. Reviews, management comments and letter versions are append-only tables
(`db/migrations/V003__auditor_workflow.sql`). `ANTHROPIC_API_KEY` switches the request reader from the keyword
fallback to Claude (docs/decisions.md D-012). Synthetic data: `python scripts/gen_synthetic_data.py`, then `make load`.

## How it fits together
```
request (PDF/email)
   └─ agent/parser        → CheckSpec[]            (LLM: split and interpret questions)
        └─ agent/checks   → Finding[] + Citation[]  (code: test evidence per account)
             ├─ agent/tools        read staging.* through a read-only role
             └─ agent/store        write audit.*   (guardrails enforced by the DB)
                  └─ agent/pack    → index, extracts, gap report, response letter
                  └─ eval/score.py → recall, false-gap rate, unsupported claims
```

| Schema | Holds | Owned by |
|---|---|---|
| `raw` | source files as provided, all TEXT, plus `_row_no` | `scripts/load_data.py` |
| `staging` | typed views, every timestamp in UTC with the original kept | `db/staging/R__*.sql` |
| `audit` | runs, checks, sampled accounts, findings, citations | `db/migrations/V*.sql` |

Guardrails the database enforces: an `evidenced` or `gap` finding cannot be committed without a
citation; a gap must have a severity; findings of a completed run cannot be changed or deleted;
the agent's SQL tool runs as a read-only role.

## Commands
`make help` lists them all. Most used: `setup`, `load`, `test`, `lint`,
`make eval RUN=<run_id> KEY=eval/gap_keys/<file>.csv`.

## Working together
Read [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md). Shared rulings are in
[docs/decisions.md](docs/decisions.md); module interfaces in [docs/contracts.md](docs/contracts.md).
