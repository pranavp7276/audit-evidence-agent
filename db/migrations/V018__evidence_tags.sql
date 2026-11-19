-- Evidence tags the audit needs and the system did not capture (config/evidence_tags.yaml), each feeding a check that now runs:
--   clock_source          which clock stamped an event (P2); every timestamp now carries its zone and its clock
--   template approval     approved_at / retired_at on the template registry          -> TPL-01 template approved at send time
--   collector status      effective-dated status history (P3), not an overwritten flag -> AGT-01 collector active on the call date
--   registered caller IDs the numbers an agency may call from, with validity          -> CLI-01 calls only from registered numbers
-- (the borrower's contact type and source, which CNT-01 needs, were already captured on customer_contact_number)

ALTER TABLE compliance.dialer_config ADD COLUMN IF NOT EXISTS clock_source text NOT NULL DEFAULT 'dialer';
ALTER TABLE cn_core.digital_template ADD COLUMN IF NOT EXISTS approved_at timestamp, ADD COLUMN IF NOT EXISTS retired_at timestamp;

CREATE TABLE compliance.collector_status (
    status_id     bigint PRIMARY KEY,
    employee_code text NOT NULL,
    status        text NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'TERMINATED')),
    valid_from    date NOT NULL,
    valid_to      date                      -- null while it still holds
);
CREATE INDEX collector_status_by_employee ON compliance.collector_status (employee_code, valid_from);

CREATE TABLE compliance.registered_cli (
    cli_id          bigint PRIMARY KEY,
    cli_number      text NOT NULL,
    organization_id int  NOT NULL,          -- the agency the number is registered to
    purpose         text NOT NULL DEFAULT 'COLLECTIONS',
    valid_from      date NOT NULL,
    valid_to        date
);
CREATE INDEX registered_cli_by_number ON compliance.registered_cli (cli_number, organization_id);

GRANT SELECT ON compliance.collector_status, compliance.registered_cli TO agent_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON compliance.collector_status, compliance.registered_cli TO audit_team;

-- four more checks (check_catalog TPL-01, AGT-01, CLI-01, CNT-01)
ALTER TABLE audit.checks DROP CONSTRAINT checks_check_type_check;
ALTER TABLE audit.checks ADD CONSTRAINT checks_check_type_check CHECK (check_type IN (
    'consent_before_contact', 'calling_hours', 'calling_frequency', 'verification_before_disclosure', 'notice_timeline', 'agent_certification', 'recording_completeness',
    'template_approval', 'collector_active', 'caller_id_registered', 'third_party_disclosure', 'other'));
ALTER TABLE audit.guardrail DROP CONSTRAINT guardrail_check_type_check;
ALTER TABLE audit.guardrail ADD CONSTRAINT guardrail_check_type_check CHECK (check_type IN (
    'consent_before_contact', 'calling_hours', 'calling_frequency', 'verification_before_disclosure', 'notice_timeline', 'agent_certification', 'recording_completeness',
    'template_approval', 'collector_active', 'caller_id_registered', 'third_party_disclosure'));

INSERT INTO audit.guardrail (check_type, version, title, obligation, source_label, applicability, parameters, required_evidence,
                             default_severity, priority_weight, effective_from, status, created_by)
VALUES
 ('template_approval', 1, 'Messages only on templates approved at send time',
  'Every message is sent on a template that was approved, and not yet retired, when it was sent.', 'Lender agency audit (check catalog TPL-01)',
  '{"channels": ["WHATSAPP", "SMS"]}', '{}', 'Message send time and template id; the template registry approval status and dates', 'Major', 1, DATE '2026-01-01', 'published', 'system'),
 ('collector_active', 1, 'Collector active on the call date',
  'The collector was an active, not terminated or inactive, collector on the date of each call.', 'Lender agency audit (check catalog AGT-01)',
  '{"channels": ["CALL"]}', '{}', 'Call session, collector employee code, collector status history', 'Major', 1, DATE '2026-01-01', 'published', 'system'),
 ('caller_id_registered', 1, 'Calls only from registered numbers',
  'Every outbound call is placed from a number registered to the agency on the call date, never from a personal mobile.', 'Lender agency audit (check catalog CLI-01)',
  '{"channels": ["CALL"]}', '{}', 'Call session, the caller number, the registered caller ID list and its validity', 'Major', 1, DATE '2026-01-01', 'published', 'system'),
 ('third_party_disclosure', 1, 'No dues disclosed to a contact the borrower did not provide',
  'A call to a reference or other contact the borrower did not provide never discloses dues.', 'Lender agency audit (check catalog CNT-01)',
  '{"channels": ["CALL"]}', '{}', 'Call session, the contact type of the dialled number, the transcript', 'Critical', 1, DATE '2026-01-01', 'published', 'system');
