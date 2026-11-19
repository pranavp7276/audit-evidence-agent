-- Auditor workflow: who asked, review of each finding, management comments and the response letter.
-- Findings stay frozen and untouched (V002). Everything an auditor adds lives in these tables, append-only:
-- a review or a letter edit adds a row, the latest row wins, nothing is overwritten or deleted, and a
-- disputed gap is still reported as a gap.

ALTER TABLE audit.runs
    ADD COLUMN IF NOT EXISTS lender       text,          -- who sent the request
    ADD COLUMN IF NOT EXISTS response_due date,
    ADD COLUMN IF NOT EXISTS created_by   text;

CREATE TABLE audit.finding_reviews (
    review_id    bigserial PRIMARY KEY,
    run_id       uuid   NOT NULL REFERENCES audit.runs(run_id),
    finding_id   bigint NOT NULL REFERENCES audit.findings(finding_id),
    reviewer     text   NOT NULL,
    disposition  text   NOT NULL CHECK (disposition IN
                     ('open', 'confirmed', 'disputed', 'remediation_planned', 'evidence_obtained')),
    comment      text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX finding_reviews_by_finding ON audit.finding_reviews (finding_id, review_id DESC);
CREATE INDEX finding_reviews_by_run ON audit.finding_reviews (run_id);

-- Management comment per question, shown next to the gaps in the response letter.
CREATE TABLE audit.question_responses (
    response_id  bigserial PRIMARY KEY,
    run_id       uuid NOT NULL REFERENCES audit.runs(run_id),
    question_ref text NOT NULL,
    author       text NOT NULL,
    body         text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX question_responses_by_run ON audit.question_responses (run_id, question_ref, response_id DESC);

-- Response letter versions: draft -> in_review -> approved.
CREATE TABLE audit.letters (
    letter_id   bigserial PRIMARY KEY,
    run_id      uuid NOT NULL REFERENCES audit.runs(run_id),
    version     int  NOT NULL,
    body        text NOT NULL,
    status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'in_review', 'approved')),
    author      text NOT NULL,
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, version)
);

GRANT SELECT ON audit.finding_reviews, audit.question_responses, audit.letters TO agent_reader;
