-- Knowledge base and guardrails.
-- Compliance uploads a circular, policy or SOP. Each independently testable obligation becomes a guardrail linked to its
-- clause, with a default severity and a priority weight. Guardrails are versioned: a change adds a row, never edits one,
-- and an audit records which version it applied. The weight only orders the review queue; it never decides an outcome,
-- and every confirmed gap is reported whatever its weight.

CREATE TABLE audit.kb_document (
    doc_id         bigserial PRIMARY KEY,
    title          text NOT NULL,
    issuer         text,
    doc_type       text NOT NULL CHECK (doc_type IN ('circular', 'policy', 'sop')),
    reference_no   text,
    effective_date date,
    body           text NOT NULL,
    uploaded_by    text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE audit.kb_clause (
    clause_id  bigserial PRIMARY KEY,
    doc_id     bigint NOT NULL REFERENCES audit.kb_document(doc_id),
    seq        int NOT NULL,
    clause_no  text NOT NULL,
    body       text NOT NULL,
    UNIQUE (doc_id, seq)
);

CREATE SEQUENCE audit.guardrail_id_seq;
CREATE TABLE audit.guardrail (
    guardrail_id      bigint NOT NULL DEFAULT nextval('audit.guardrail_id_seq'),
    version           int    NOT NULL,
    check_type        text   NOT NULL CHECK (check_type IN (
                          'consent_before_contact', 'calling_hours', 'calling_frequency', 'verification_before_disclosure',
                          'notice_timeline', 'agent_certification', 'recording_completeness')),
    title             text   NOT NULL,
    obligation        text   NOT NULL,                  -- the requirement in plain words
    source_doc_id     bigint REFERENCES audit.kb_document(doc_id),
    source_clause     text,                             -- clause number or page in the source
    source_label      text,                             -- where it comes from when there is no uploaded document (e.g. D12)
    applicability     jsonb  NOT NULL DEFAULT '{}',     -- lender, portfolio or agency, channel
    parameters        jsonb  NOT NULL DEFAULT '{}',     -- extracted limits, for reference: the tests read D12 rule rows
    required_evidence text,
    default_severity  text   NOT NULL,
    priority_weight   int    NOT NULL DEFAULT 1 CHECK (priority_weight BETWEEN 1 AND 3),
    weight_reason     text,
    effective_from    date   NOT NULL,
    status            text   NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'retired')),
    created_by        text   NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (guardrail_id, version),
    CONSTRAINT weight_needs_reason CHECK (priority_weight = 1 OR COALESCE(btrim(weight_reason), '') <> '')
);
CREATE INDEX guardrail_by_type ON audit.guardrail (check_type, status);

-- The seven checks the platform runs, as published guardrails (version 1), weight 1, sourced from D12 and the audit brief.
INSERT INTO audit.guardrail (check_type, version, title, obligation, source_label, applicability, parameters, required_evidence,
                             default_severity, priority_weight, effective_from, status, created_by)
VALUES
 ('consent_before_contact', 1, 'WhatsApp and SMS consent before contact',
  'Every message is preceded by valid consent for the recipient number, channel and purpose.', 'Audit brief CO-04',
  '{"channels": ["WHATSAPP", "SMS"]}', '{}', 'Message send event, recipient, consent history, template category', 'Critical', 1, DATE '2026-01-01', 'published', 'system'),
 ('calling_hours', 1, 'Calls within permitted hours',
  'Calls are placed only inside the calling window in force on the day, in the borrower''s local time.', 'D12 policy rules',
  '{"channels": ["CALL"]}', '{"rule_keys": ["calling_window_start", "calling_window_end"]}', 'Call session start time and source zone; the D12 rule effective that day', 'Critical', 1, DATE '2026-01-01', 'published', 'system'),
 ('calling_frequency', 1, 'Call attempts within the daily cap',
  'No contact number receives more eligible call attempts in a day than the cap in force that day.', 'D12 policy rules',
  '{"channels": ["CALL"], "counting_unit": "CONTACT_NUMBER"}', '{"rule_keys": ["max_attempts_per_contact_per_day"]}', 'Dialer session ids, contact number, start time, outcome; the D12 rule', 'Critical', 1, DATE '2026-01-01', 'published', 'system'),
 ('verification_before_disclosure', 1, 'Identity verified before dues disclosed',
  'The borrower''s identity is verified before the first disclosure of dues on a call.', 'Audit brief CO-04',
  '{"channels": ["CALL"]}', '{}', 'Recording and transcript for the session with timestamps', 'Critical', 1, DATE '2026-01-01', 'published', 'system'),
 ('notice_timeline', 1, 'Notices dispatched and served on time',
  'Each notice is dispatched and served within the business days allowed from its trigger.', 'D12 policy rules',
  '{}', '{"rule_keys": ["notice_dispatch_sla_business_days", "notice_service_sla_business_days"]}', 'Trigger, dispatch and service dates; the holiday calendar', 'Major', 1, DATE '2026-01-01', 'published', 'system'),
 ('agent_certification', 1, 'Recovery agent certified on the call date',
  'The collector held a valid certificate on the date of each call.', 'Audit brief CO-04',
  '{}', '{}', 'Call session, collector employee code, certification validity dates', 'Major', 1, DATE '2026-01-01', 'published', 'system'),
 ('recording_completeness', 1, 'Recording retained for every connected call',
  'Every connected call has a recording in the recording store.', 'Audit brief CO-04',
  '{}', '{}', 'Connected call sessions and the recording store retrieval status', 'Minor', 1, DATE '2026-01-01', 'published', 'system');

GRANT SELECT ON audit.kb_document, audit.kb_clause, audit.guardrail TO agent_reader;
