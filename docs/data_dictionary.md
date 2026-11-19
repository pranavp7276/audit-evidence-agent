# Data dictionary

The platform now audits a CN Core replica. The tables, columns, relationships, time zones and what is real versus assumed are in
[cn_core_model.md](cn_core_model.md). The typed views the agent reads (`staging.*`, all timestamps in UTC with the original value and
zone kept) are defined in `db/staging/R__1*.sql`.

The earlier loose-file dataset (`raw.*`) was removed (docs/decisions.md D-029). Which evidence tag lives in which column is in
[evidence_coverage.md](evidence_coverage.md), generated from `config/source_map.yaml`.
