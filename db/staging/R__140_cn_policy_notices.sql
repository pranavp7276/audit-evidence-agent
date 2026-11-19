-- D12 rules (effective-dated), holidays, notices, collectors and certificates.
CREATE OR REPLACE VIEW staging.policy_rules AS
SELECT p.rule_id::text AS rule_id, p.policy_code, p.rule_key, p.rule_value, p.unit, p.counting_unit, p.counting_rule,
       p.effective_from, p.effective_to, p.note, p.institution_code
FROM compliance.calling_policy_rule p;

CREATE OR REPLACE VIEW staging.holidays AS
SELECT h.holiday_id::text AS holiday_id, h.holiday_date, h.holiday_name, h.scope, h.state FROM compliance.holiday_calendar h;

CREATE OR REPLACE VIEW staging.notices AS
SELECT n.notice_id::text AS notice_id, n.account_id::text AS account_id, n.notice_type, n.borrower_state,
       n.trigger_date, n.dispatch_date, n.served_date, n.dispatch_mode
FROM compliance.notice n;

-- The collector as the contact log knows them (user id) and as the certification register knows them (employee code).
DROP VIEW IF EXISTS staging.collectors;
CREATE VIEW staging.collectors AS
SELECT u.user_id::text AS user_id, u.employee_code, u.user_status, o.organization_name AS agency, o.organization_code AS agency_code
FROM uamdb.users u
JOIN uamdb.organization o ON o.organization_id = u.organization_id;

CREATE OR REPLACE VIEW staging.certifications AS
SELECT c.cert_id::text AS cert_id, c.employee_code, c.certification, c.certificate_no, c.valid_from, c.valid_to, c.issuer
FROM compliance.collector_certification c;

DROP VIEW IF EXISTS staging.dialers;
CREATE VIEW staging.dialers AS
SELECT d.dialer_code, d.dialer_name, d.timezone, d.clock_source FROM compliance.dialer_config d;

-- Effective-dated collector status (a collector's status on a call date), the numbers an agency may call from, and the template registry with its approval dates.
CREATE OR REPLACE VIEW staging.collector_status AS
SELECT c.status_id::text AS status_id, c.employee_code, c.status, c.valid_from, c.valid_to FROM compliance.collector_status c;

CREATE OR REPLACE VIEW staging.registered_clis AS
SELECT r.cli_id::text AS cli_id, r.cli_number, o.organization_code AS agency_code, r.purpose, r.valid_from, r.valid_to
FROM compliance.registered_cli r JOIN uamdb.organization o ON o.organization_id = r.organization_id;

DROP VIEW IF EXISTS staging.templates;
CREATE VIEW staging.templates AS
SELECT t.template_id::text AS template_id, t.sms_category, t.digital_channel, t.approval_status, t.approved_at, t.retired_at
FROM cn_core.digital_template t;
