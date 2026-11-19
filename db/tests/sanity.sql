-- Run with: psql "$DATABASE_URL" -f db/tests/sanity.sql
-- Add a query per staging view as you build it. Each should return zero rows.

-- 1. Findings that claim something without a record (must be empty).
SELECT 'unsupported_claims' AS test, count(*) AS bad_rows FROM audit.v_unsupported_claims;

-- 2. Gaps without severity (blocked by constraint, kept as a smoke test).
SELECT 'gaps_without_severity' AS test, count(*) FROM audit.findings
WHERE status = 'gap' AND severity IS NULL;

-- Examples to enable once staging exists:
-- SELECT 'd4_null_ts' AS test, count(*) FROM staging.d4_contacts WHERE contact_ts_utc IS NULL;
-- SELECT 'd4_unknown_collector', count(*) FROM staging.d4_contacts c
--   LEFT JOIN staging.collector_roster r USING (collector_id) WHERE r.collector_id IS NULL;
