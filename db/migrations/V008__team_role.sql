-- A login for teammates: read and write the data, run the platform locally, but never change the structure.
-- The password is NOT set here (a migration is committed to git): the database owner sets it once with
--   ALTER ROLE audit_team WITH LOGIN PASSWORD '...';
-- and shares it privately.
--
--   cn_core, uamdb, compliance   select, insert, update, delete (the data the audit tests)
--   audit                        select, insert, update (a local run writes its audit records; findings of a completed run are
--                                frozen by a trigger; no delete)
--   staging, raw                 select
--   sandbox                      full control: a place to create their own tables
-- No DDL on the other schemas, no TRUNCATE, no DROP, no role management.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_team') THEN
        CREATE ROLE audit_team NOLOGIN;
    END IF;
END $$;

ALTER ROLE audit_team SET statement_timeout = '60s';
ALTER ROLE audit_team CONNECTION LIMIT 25;

CREATE SCHEMA IF NOT EXISTS sandbox;

GRANT USAGE ON SCHEMA uamdb, cn_core, compliance, audit, staging, raw TO audit_team;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA uamdb, cn_core, compliance TO audit_team;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA audit TO audit_team;
GRANT SELECT ON ALL TABLES IN SCHEMA staging, raw TO audit_team;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA uamdb, cn_core, compliance, audit TO audit_team;
GRANT ALL ON SCHEMA sandbox TO audit_team;
GRANT ALL ON ALL TABLES IN SCHEMA sandbox TO audit_team;

-- tables and sequences created later by the owner (new migrations) are covered too
ALTER DEFAULT PRIVILEGES IN SCHEMA uamdb, cn_core, compliance GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO audit_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA audit GRANT SELECT, INSERT, UPDATE ON TABLES TO audit_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA staging, raw GRANT SELECT ON TABLES TO audit_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA uamdb, cn_core, compliance, audit GRANT USAGE, SELECT ON SEQUENCES TO audit_team;

-- the agent's read-only mode does SET ROLE agent_reader (agent/db.py)
DO $$
BEGIN
    BEGIN
        EXECUTE 'GRANT agent_reader TO audit_team WITH SET TRUE, INHERIT FALSE';  -- PostgreSQL 16+
    EXCEPTION WHEN OTHERS THEN
        BEGIN
            EXECUTE 'GRANT agent_reader TO audit_team';
        EXCEPTION WHEN OTHERS THEN
            NULL;
        END;
    END;
END $$;
