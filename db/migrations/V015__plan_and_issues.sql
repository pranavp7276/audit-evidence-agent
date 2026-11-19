-- Two registers an audit team keeps beside the findings.
--
-- The audit plan: audits and readiness checks that are expected, with who owns them and when they are due. A plan row is not evidence and may be edited;
-- when the audit it describes is started, the run is linked to it.
--
-- Issues: a gap that has been confirmed becomes a tracked item with an owner, a due date and a status, until it is resolved and verified. An issue only
-- points at findings; it never changes one. Every change to an issue adds an event, and events are never edited.

CREATE TABLE audit.audit_plan (
    plan_id      bigserial PRIMARY KEY,
    title        text NOT NULL,
    lender       text,
    scope        text,
    kind         text NOT NULL DEFAULT 'audit' CHECK (kind IN ('audit', 'readiness')),
    planned_start date,
    due_date     date,
    owner        text,
    recurrence   text NOT NULL DEFAULT 'none' CHECK (recurrence IN ('none', 'monthly', 'quarterly', 'yearly')),
    status       text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'in_progress', 'done', 'cancelled')),
    run_id       uuid REFERENCES audit.runs(run_id),
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_plan_by_due ON audit.audit_plan (due_date);

CREATE TABLE audit.issues (
    issue_id    bigserial PRIMARY KEY,
    title       text NOT NULL,
    description text,
    check_type  text,
    severity    text,
    owner       text,
    due_date    date,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'verified', 'wont_fix')),
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX issues_by_status ON audit.issues (status, due_date);

CREATE TABLE audit.issue_findings (
    issue_id   bigint NOT NULL REFERENCES audit.issues(issue_id),
    finding_id bigint NOT NULL REFERENCES audit.findings(finding_id),
    PRIMARY KEY (issue_id, finding_id)
);
CREATE INDEX issue_findings_by_finding ON audit.issue_findings (finding_id);

CREATE TABLE audit.issue_events (
    event_id   bigserial PRIMARY KEY,
    issue_id   bigint NOT NULL REFERENCES audit.issues(issue_id),
    actor      text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('created', 'status', 'owner', 'due', 'note')),
    body       text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX issue_events_by_issue ON audit.issue_events (issue_id, event_id);

GRANT SELECT ON audit.audit_plan, audit.issues, audit.issue_findings, audit.issue_events TO agent_reader;
GRANT SELECT, INSERT, UPDATE ON audit.audit_plan, audit.issues TO audit_team;
GRANT SELECT, INSERT ON audit.issue_findings, audit.issue_events TO audit_team;
GRANT USAGE, SELECT ON SEQUENCE audit.audit_plan_plan_id_seq, audit.issues_issue_id_seq, audit.issue_events_event_id_seq TO audit_team;
