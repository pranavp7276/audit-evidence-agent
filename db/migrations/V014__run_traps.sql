-- The subtle-evidence traps each audit caught, counted once when the audit completes (a completed audit never changes), so the dashboard reads
-- a few rows instead of re-reading every finding.
CREATE TABLE audit.run_traps (
    run_id          uuid NOT NULL REFERENCES audit.runs(run_id),
    trap_key        text NOT NULL,
    n               int  NOT NULL,
    example_finding bigint,
    extra           jsonb NOT NULL DEFAULT '{}',
    PRIMARY KEY (run_id, trap_key)
);
GRANT SELECT ON audit.run_traps TO agent_reader;
GRANT SELECT, INSERT, DELETE ON audit.run_traps TO audit_team;
