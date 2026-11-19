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
CREATE OR REPLACE VIEW staging.collectors AS
SELECT u.user_id::text AS user_id, u.employee_code, u.user_status, o.organization_name AS agency, o.organization_code AS agency_code, r.role_name
FROM uamdb.users u
JOIN uamdb.organization o ON o.organization_id = u.organization_id
LEFT JOIN uamdb.roles r ON r.role_id = u.role_id;

CREATE OR REPLACE VIEW staging.certifications AS
SELECT c.cert_id::text AS cert_id, c.employee_code, c.certification, c.certificate_no, c.valid_from, c.valid_to, c.issuer
FROM compliance.collector_certification c;

CREATE OR REPLACE VIEW staging.dialers AS
SELECT d.dialer_code, d.dialer_name, d.timezone FROM compliance.dialer_config d;
