# Data dictionary

The platform now audits a CN Core replica. The tables, columns, relationships, time zones and what is real versus assumed are in
[cn_core_model.md](cn_core_model.md). The typed views the agent reads (`staging.*`, all timestamps in UTC with the original value and
zone kept) are defined in `db/staging/R__1*.sql`.

The loose CSV files in `data/` (`raw.*`, from `scripts/gen_synthetic_data.py`) are the earlier synthetic dataset; they are still
loadable but nothing reads them.
