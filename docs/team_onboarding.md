# Team onboarding: connect to the shared database

The platform's data lives in one shared Supabase Postgres. Teammates connect with the **`audit_team`** login, not the owner's.
The password is shared privately by the database owner; it is never committed.

## What `audit_team` can and cannot do

| Can | Cannot |
|---|---|
| Read everything | Drop, alter or truncate any table |
| Insert, update and delete rows in `cn_core`, `uamdb`, `compliance` (the data the audit tests) | Create tables in those schemas (the structure changes only through migrations) |
| Run the platform locally (it writes its own `audit.*` records) | Delete audit findings or edit the findings of a completed run |
| Create and drop their own tables in the `sandbox` schema | Create roles or touch other people's logins |

## Connect

1. In the repo (branch `synthetic-data-and-agent` or its successor): `python -m venv .venv`, activate it, `pip install -e ".[dev]"`.
2. `cp .env.example .env` and set `DATABASE_URL` to the connection string the owner gave you (it starts with `postgresql://audit_team.`).
3. Check it: `python -m pytest -q` (all pass) and `python -m agent serve`, then open http://127.0.0.1:8000.

The address is the Supabase **session pooler** (port 5432), reachable from the internet; nothing needs to be made public. If your network
blocks port 5432, tell the owner. Do not switch to the transaction pooler (port 6543): the agent's read-only mode needs a session.

## Adding data

Use the Supabase **Table Editor** (pick the schema in the dropdown, e.g. `cn_core`) or SQL. For example, a new customer and loan:

```sql
insert into cn_core.customer (id, institution_code, customer_number, customer_name, branch_code)
values (5900001, 'CNFIN', 'C900000001', 'Test Borrower', 'BR01');
insert into cn_core.account (id, institution_code, account_number, customer_id, account_status_id)
values (7900001, 'CNFIN', 'CNF900000001', 5900001, 1);
```

Keep rows consistent with the generated data (a call needs a `tele_process_instance_call_logs` row **and** a `tele_process_instance_activity` row; a
message needs a `communication_dashboard_t` row and, for the consent check, a `compliance.customer_consent` row for the recipient number). Use
**synthetic data only**. Put scratch tables in `sandbox`.

## Do not run against the shared database

- `scripts/gen_book.py` and `scripts/load_data.py` replace everyone's data. They refuse to run on a shared database unless `ALLOW_RELOAD=1` is set, and
  `audit_team` could not truncate anyway. Run them only against your own local Postgres.
- `scripts/migrate.py --reset` drops the schemas.
- Never edit a migration file that already exists. A change to the structure is a new file `V0NN__name.sql`; the owner applies it.

## Rules the platform keeps (see CLAUDE.md)

No compliance claim without a cited record; gaps are never dropped or softened; timestamps are compared in UTC; limits come from the D12 rows, never code.
