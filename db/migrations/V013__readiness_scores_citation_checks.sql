-- What the story needs to show: which runs are readiness checks (run before any auditor asks), how a run scored against its answer key,
-- and whether every citation was re-read from the warehouse. All append-only or written once.

ALTER TABLE audit.runs ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'audit' CHECK (kind IN ('audit', 'readiness'));

-- A score against a known answer key. The latest row for a run is the one shown.
CREATE TABLE audit.run_scores (
    score_id         bigserial PRIMARY KEY,
    run_id           uuid NOT NULL REFERENCES audit.runs(run_id),
    key_name         text NOT NULL,
    true_gaps        int  NOT NULL,
    reported_gaps    int  NOT NULL,
    matched          int  NOT NULL,
    false_gaps       int  NOT NULL,
    unsupported      int  NOT NULL,
    recall           numeric(6, 4) NOT NULL,
    false_gap_rate   numeric(6, 4) NOT NULL,
    scored_by        text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX run_scores_by_run ON audit.run_scores (run_id, score_id DESC);

-- Every cited record, looked up again in the warehouse after the findings were written.
CREATE TABLE audit.citation_checks (
    run_id      uuid PRIMARY KEY REFERENCES audit.runs(run_id),
    checked     int NOT NULL,
    verified    int NOT NULL,
    missing     jsonb NOT NULL DEFAULT '[]',
    created_at  timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT ON audit.run_scores, audit.citation_checks TO agent_reader;
GRANT SELECT, INSERT ON audit.run_scores, audit.citation_checks TO audit_team;
GRANT USAGE, SELECT ON SEQUENCE audit.run_scores_score_id_seq TO audit_team;

ALTER TABLE audit.agent_steps DROP CONSTRAINT agent_steps_phase_check;
ALTER TABLE audit.agent_steps ADD CONSTRAINT agent_steps_phase_check
    CHECK (phase IN ('plan', 'retrieve', 'evaluate', 'investigate', 'verify', 'challenge', 'report'));
