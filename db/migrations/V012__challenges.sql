-- A second reading of each reported gap: a model is shown only the records the gap cites and says whether they support it.
-- It never changes a finding or its severity; a disagreement only moves the gap to the top of the review queue. Append-only.
CREATE TABLE audit.finding_challenges (
    challenge_id bigserial PRIMARY KEY,
    run_id       uuid   NOT NULL REFERENCES audit.runs(run_id),
    finding_id   bigint NOT NULL REFERENCES audit.findings(finding_id),
    verdict      text   NOT NULL CHECK (verdict IN ('supports', 'disputes', 'unclear')),
    concern      text,                     -- one sentence; quotes a cited field when the verdict is not 'supports'
    model        text   NOT NULL,
    requested_by text,                     -- null when made automatically at the end of a run
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finding_challenges_by_finding ON audit.finding_challenges (finding_id, challenge_id DESC);
CREATE INDEX finding_challenges_by_run ON audit.finding_challenges (run_id);
GRANT SELECT ON audit.finding_challenges TO agent_reader;
GRANT SELECT, INSERT ON audit.finding_challenges TO audit_team;
GRANT USAGE, SELECT ON SEQUENCE audit.finding_challenges_challenge_id_seq TO audit_team;

-- The trace gains a phase for this pass, and the team role can write it (V011 was added after the team grants).
ALTER TABLE audit.agent_steps DROP CONSTRAINT agent_steps_phase_check;
ALTER TABLE audit.agent_steps ADD CONSTRAINT agent_steps_phase_check CHECK (phase IN ('plan', 'retrieve', 'evaluate', 'investigate', 'challenge', 'report'));
GRANT SELECT, INSERT ON audit.agent_steps TO audit_team;
GRANT USAGE, SELECT ON SEQUENCE audit.agent_steps_step_id_seq TO audit_team;
