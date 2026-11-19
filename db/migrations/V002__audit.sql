-- Agent outputs. The guardrails from the problem statement are enforced here, in the
-- database, so no code path can skip them:
--   * an 'evidenced' or 'gap' finding cannot be committed without at least one citation
--   * a 'gap' must carry a severity from the request's scale
--   * findings are never deleted or softened: status changes are blocked once a run is final

CREATE TABLE audit.runs (
    run_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id      text        NOT NULL,             -- e.g. 'PUB-01', 'HID-03'
    request_source  text        NOT NULL CHECK (request_source IN ('pdf', 'email', 'text')),
    request_path    text,
    severity_scale  jsonb       NOT NULL DEFAULT '[]', -- as given in the request, ordered
    agent_version   text,                              -- git sha of the code that ran
    status          text        NOT NULL DEFAULT 'running'
                                CHECK (status IN ('running', 'completed', 'failed')),
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    notes           text
);

CREATE TABLE audit.checks (
    run_id            uuid NOT NULL REFERENCES audit.runs(run_id),
    check_id          text NOT NULL,                  -- stable within a run, e.g. 'Q3b'
    question_ref      text NOT NULL,                  -- where in the request it came from
    question_text     text NOT NULL,                  -- the wording it was derived from
    check_type        text NOT NULL CHECK (check_type IN (
                          'consent_before_contact',
                          'calling_hours',
                          'calling_frequency',
                          'verification_before_disclosure',
                          'notice_timeline',
                          'agent_certification',
                          'recording_completeness',
                          'other')),
    sample_definition jsonb NOT NULL,                 -- how the accounts were chosen
    test_definition   jsonb NOT NULL,                 -- what passes, in plain terms + params
    sources           text[] NOT NULL,                -- e.g. {D4,D5}
    PRIMARY KEY (run_id, check_id)
);

CREATE TABLE audit.sample_accounts (
    run_id     uuid NOT NULL,
    check_id   text NOT NULL,
    account_id text NOT NULL,
    PRIMARY KEY (run_id, check_id, account_id),
    FOREIGN KEY (run_id, check_id) REFERENCES audit.checks(run_id, check_id)
);

CREATE TABLE audit.findings (
    finding_id      bigserial PRIMARY KEY,
    run_id          uuid NOT NULL,
    check_id        text NOT NULL,
    account_id      text NOT NULL,
    subject_ref     text,          -- the event tested, if finer than account (message id, call id)
    status          text NOT NULL CHECK (status IN ('evidenced', 'gap', 'cannot_determine')),
    severity        text,          -- label from runs.severity_scale; required for gaps
    reason          text NOT NULL, -- one or two plain sentences, no softening
    evidence_query  text,          -- the SQL / tool call that produced it, for reproducibility
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (run_id, check_id) REFERENCES audit.checks(run_id, check_id),
    CONSTRAINT gap_needs_severity CHECK (status <> 'gap' OR severity IS NOT NULL)
);
CREATE UNIQUE INDEX findings_one_per_subject
    ON audit.findings (run_id, check_id, account_id, COALESCE(subject_ref, ''));

CREATE TABLE audit.citations (
    citation_id        bigserial PRIMARY KEY,
    finding_id         bigint NOT NULL REFERENCES audit.findings(finding_id) ON DELETE CASCADE,
    source_system      text NOT NULL CHECK (source_system IN (
                           'D4', 'D5', 'D10', 'D11', 'D12',
                           'notice_dispatch', 'cert_register', 'collector_roster',
                           'holiday_calendar', 'template_registry', 'recording_store',
                           'transcript_store', 'consent_registry', 'contact_log')),
    source_table       text NOT NULL,  -- raw.<table> the record lives in
    record_key         text NOT NULL,  -- primary key (or _row_no) of that record
    record_ts_utc      timestamptz,    -- the timestamp used in the test, normalised
    record_ts_original text,           -- the same timestamp as it appears in the source
    extract            jsonb,          -- only the fields the request needs (data minimisation)
    role               text NOT NULL DEFAULT 'primary' CHECK (role IN ('primary', 'supporting'))
);
CREATE INDEX citations_by_finding ON audit.citations (finding_id);

-- Guardrail: evidenced and gap findings must cite at least one record.
-- Deferred to commit so a finding and its citations can be inserted in one transaction.
CREATE FUNCTION audit.require_citation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status IN ('evidenced', 'gap') AND NOT EXISTS (
        SELECT 1 FROM audit.citations c WHERE c.finding_id = NEW.finding_id
    ) THEN
        RAISE EXCEPTION 'Finding % (% / % / %) has status % but no citation. No claim without a cited record.',
            NEW.finding_id, NEW.check_id, NEW.account_id, COALESCE(NEW.subject_ref, '-'), NEW.status
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER findings_require_citation
    AFTER INSERT OR UPDATE ON audit.findings
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION audit.require_citation();

-- Guardrail: once a run is completed, its findings are frozen (no dropping, no softening).
CREATE FUNCTION audit.freeze_completed_runs() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    run_status text;
BEGIN
    SELECT status INTO run_status FROM audit.runs WHERE run_id = OLD.run_id;
    IF run_status = 'completed' THEN
        RAISE EXCEPTION 'Run % is completed; findings cannot be changed or deleted. Start a new run.',
            OLD.run_id USING ERRCODE = 'check_violation';
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$;

CREATE TRIGGER findings_frozen_after_completion
    BEFORE UPDATE OR DELETE ON audit.findings
    FOR EACH ROW EXECUTE FUNCTION audit.freeze_completed_runs();

-- Views the pack writer and the eval read from.
CREATE VIEW audit.v_gap_report AS
SELECT f.run_id, r.request_id, c.question_ref, c.check_id, c.check_type,
       f.account_id, f.subject_ref, f.severity, f.reason,
       count(ci.citation_id) AS citation_count
FROM audit.findings f
JOIN audit.checks c USING (run_id, check_id)
JOIN audit.runs r   USING (run_id)
LEFT JOIN audit.citations ci ON ci.finding_id = f.finding_id
WHERE f.status = 'gap'
GROUP BY f.finding_id, r.request_id, c.question_ref, c.check_id, c.check_type;

CREATE VIEW audit.v_check_summary AS
SELECT f.run_id, f.check_id, c.question_ref, c.check_type,
       count(*) FILTER (WHERE f.status = 'evidenced')        AS evidenced,
       count(*) FILTER (WHERE f.status = 'gap')              AS gaps,
       count(*) FILTER (WHERE f.status = 'cannot_determine') AS cannot_determine,
       count(*)                                              AS total
FROM audit.findings f
JOIN audit.checks c USING (run_id, check_id)
GROUP BY f.run_id, f.check_id, c.question_ref, c.check_type;

-- Should always be empty. The eval reports its row count as "unsupported claims".
CREATE VIEW audit.v_unsupported_claims AS
SELECT f.*
FROM audit.findings f
WHERE f.status IN ('evidenced', 'gap')
  AND NOT EXISTS (SELECT 1 FROM audit.citations c WHERE c.finding_id = f.finding_id);

GRANT SELECT ON ALL TABLES IN SCHEMA audit TO agent_reader;
