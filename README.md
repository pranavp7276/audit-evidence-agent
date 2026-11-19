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
