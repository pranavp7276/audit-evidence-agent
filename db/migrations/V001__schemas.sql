-- Three layers. See docs/decisions.md (D-001).
--   raw      : source files exactly as provided, every column TEXT. Owned by scripts/load_data.py.
--   staging  : typed, cleaned views over raw. All timestamps UTC. Owned by db/staging/*.sql.
--   audit    : what the agent produced (runs, checks, findings, citations). Owned by migrations.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS audit;

-- Every session works in UTC unless it says otherwise.
DO $$
BEGIN
  EXECUTE format('ALTER DATABASE %I SET timezone TO %L', current_database(), 'UTC');
END $$;

-- Read-only role for the agent's warehouse_sql tool. It can read raw and staging,
-- and read audit, but cannot write anywhere. Writes go through agent/store.py.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
    CREATE ROLE agent_reader NOLOGIN;
  END IF;
END $$;
GRANT USAGE ON SCHEMA raw, staging, audit TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw     GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit   GRANT SELECT ON TABLES TO agent_reader;
