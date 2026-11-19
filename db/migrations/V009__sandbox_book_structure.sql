-- The common sandbox "CN book" (datasets D1 to D13): about 100,000 delinquent accounts across three fictional lenders
-- (a bank, an NBFC and an MFI) with 12 months of history. Table names stay CN Core's. Where CN Core already has a table for a
-- dataset it is used (customer_address, customer_email, branch, institution, lender, account_payment_schedule) with only the
-- missing columns added (marked "ext"); genuinely new datasets get new tables in the same style. The `book` schema exposes
-- the sandbox's own field names for D1 to D13 as views over them.
--
--   D1 account master       cn_core.account (+ city, flags)          book.d1_account_master
--   D2 borrower master      cn_core.customer, customer_contact_number, customer_email, customer_address, customer_name_variant
--   D3 repayment history    cn_core.account_payment_schedule (+ paid columns)
--   D4 contact history      cn_core.tele_process_instance_call_logs (+ activity bridge) and communication_dashboard_t
--   D5 call transcripts     compliance.call_transcript_segment (+ language, ASR confidence)
--   D6 PTP ledger           cn_core.ptp_ledger
--   D7 payment feed         cn_core.payment_feed
--   D8 AA bank statements   cn_core.aa_bank_statement
--   D9 bureau snapshot      cn_core.bureau_snapshot, bureau_tradeline
--   D10 consent and DND     compliance.consent_dnd_registry (borrower level) over compliance.customer_consent (events)
--   D11 template registry   cn_core.digital_template (+ language, approval status)
--   D12 policy library      audit.kb_document / kb_clause (documents) and compliance.calling_policy_rule (structured, per lender)
--   D13 channel cost        cn_core.channel_cost_capacity

CREATE SCHEMA IF NOT EXISTS book;

-- ---------------------------------------------------------------- lenders, branches
CREATE TABLE IF NOT EXISTS cn_core.institution (
    institution_code text PRIMARY KEY,
    institution_name text,               -- ext
    lender_type      text                -- ext: BANK, NBFC or MFI
);
CREATE TABLE IF NOT EXISTS cn_core.lender (
    lender_name      text PRIMARY KEY,
    institution_code text,               -- ext
    lender_type      text                -- ext
);
CREATE TABLE IF NOT EXISTS cn_core.branch (
    branch_code    text PRIMARY KEY,
    branch_name    text,
    branch_address text,
    city_code      text,
    district_code  text,
    state_code     text,
    postal_code    text,
    country_code   text,
    city           text,                 -- ext
    institution_code text                -- ext
);

-- ---------------------------------------------------------------- D1 account master: flags and city
ALTER TABLE cn_core.account
    ADD COLUMN IF NOT EXISTS city              text,
    ADD COLUMN IF NOT EXISTS restructured_flag char(1),
    ADD COLUMN IF NOT EXISTS settlement_flag   char(1),
    ADD COLUMN IF NOT EXISTS legal_flag        char(1);
CREATE INDEX IF NOT EXISTS account_institution_ix ON cn_core.account (institution_code);

-- ---------------------------------------------------------------- D2 borrower master
ALTER TABLE cn_core.customer
    ADD COLUMN IF NOT EXISTS deceased_flag char(1),
    ADD COLUMN IF NOT EXISTS deceased_date date;
ALTER TABLE cn_core.customer_contact_number
    ADD COLUMN IF NOT EXISTS source        text,    -- ext: where the number came from (LOS, BUREAU, FIELD_VISIT, CUSTOMER_APP, ...)
    ADD COLUMN IF NOT EXISTS captured_date date;    -- ext
CREATE TABLE IF NOT EXISTS cn_core.customer_name_variant (   -- ext
    id           bigint PRIMARY KEY,
    customer_id  bigint NOT NULL REFERENCES cn_core.customer,
    variant_name text NOT NULL,
    variant_type text
);
CREATE INDEX IF NOT EXISTS customer_name_variant_ix ON cn_core.customer_name_variant (customer_id);
CREATE TABLE IF NOT EXISTS cn_core.customer_address (
    id            bigint PRIMARY KEY,
    customer_id   bigint NOT NULL REFERENCES cn_core.customer,
    category      text,
    sequence_no   int,
    address_type  text,
    address_line_1 text,
    address_line_2 text,
    city          text,
    state         text,
    postal_code   text,
    landmark      text
);
CREATE INDEX IF NOT EXISTS customer_address_ix ON cn_core.customer_address (customer_id);
CREATE TABLE IF NOT EXISTS cn_core.customer_email (
    id              bigint PRIMARY KEY,
    customer_id     bigint NOT NULL REFERENCES cn_core.customer,
    category        text,
    sequence_no     int,
    email_type      text,
    email           text NOT NULL,
    verified_status text
);
CREATE INDEX IF NOT EXISTS customer_email_ix ON cn_core.customer_email (customer_id);

-- ---------------------------------------------------------------- D3 repayment history
CREATE TABLE IF NOT EXISTS cn_core.account_payment_schedule (
    id                    bigint PRIMARY KEY,
    account_id            bigint NOT NULL REFERENCES cn_core.account,
    due_type              text,
    due_date              date,
    due_amount            numeric(21,3),
    principal_due_amount  numeric(21,3),
    interest_due_amount   numeric(21,3),
    amount_paid           numeric(21,3),          -- ext
    paid_date             date,                   -- ext
    payment_mode          text,                   -- ext
    bounce_reason         text                    -- ext
);
CREATE INDEX IF NOT EXISTS aps_account_ix ON cn_core.account_payment_schedule (account_id, due_date);

-- ---------------------------------------------------------------- D6 PTP ledger, D7 payment feed
CREATE TABLE IF NOT EXISTS cn_core.ptp_ledger (          -- ext
    ptp_id          bigint PRIMARY KEY,
    account_id      bigint NOT NULL REFERENCES cn_core.account,
    promised_date   date NOT NULL,
    promised_amount numeric(21,3) NOT NULL,
    channel         text,
    captured_by     bigint,
    captured_ts     timestamp,
    status          text NOT NULL CHECK (status IN ('kept', 'partial', 'broken')),
    amount_paid     numeric(21,3)
);
CREATE INDEX IF NOT EXISTS ptp_account_ix ON cn_core.ptp_ledger (account_id);
CREATE TABLE IF NOT EXISTS cn_core.payment_feed (        -- ext
    txn_id               bigint PRIMARY KEY,
    account_id           bigint REFERENCES cn_core.account,
    source               text NOT NULL CHECK (source IN ('UPI', 'NACH', 'PAYMENT_LINK', 'AGENCY_CASH')),
    amount               numeric(21,3) NOT NULL,
    txn_ts               timestamp NOT NULL,          -- Asia/Kolkata
    payer_name           text,
    payer_handle_masked  text,
    reference_text       text,
    status               text NOT NULL,
    reversal_flag        char(1) NOT NULL DEFAULT 'N'
);
CREATE INDEX IF NOT EXISTS payment_feed_account_ix ON cn_core.payment_feed (account_id);

-- ---------------------------------------------------------------- D8 AA bank statements, D9 bureau
CREATE TABLE IF NOT EXISTS cn_core.aa_bank_statement (   -- ext
    stmt_id           bigint PRIMARY KEY,
    customer_id       bigint NOT NULL REFERENCES cn_core.customer,
    txn_date          date NOT NULL,
    narration         text,
    debit             numeric(21,3),
    credit            numeric(21,3),
    balance           numeric(21,3),
    counterparty_hint text
);
CREATE INDEX IF NOT EXISTS aa_stmt_customer_ix ON cn_core.aa_bank_statement (customer_id, txn_date);
CREATE TABLE IF NOT EXISTS cn_core.bureau_snapshot (     -- ext
    snapshot_id        bigint PRIMARY KEY,
    customer_id        bigint NOT NULL REFERENCES cn_core.customer,
    snapshot_month     date NOT NULL,
    bureau_score       int,
    enquiries_30d      int,
    enquiries_90d      int,
    utilisation_pct    numeric(6,2),
    reported_phone     text,
    reported_address   text
);
CREATE INDEX IF NOT EXISTS bureau_snapshot_ix ON cn_core.bureau_snapshot (customer_id, snapshot_month);
CREATE TABLE IF NOT EXISTS cn_core.bureau_tradeline (    -- ext
    tradeline_id       bigint PRIMARY KEY,
    snapshot_id        bigint NOT NULL REFERENCES cn_core.bureau_snapshot,
    lender_type        text,
    product            text,
    sanctioned_amount  numeric(21,3),
    outstanding_amount numeric(21,3),
    dpd_string         text,
    opened_date        date
);
CREATE INDEX IF NOT EXISTS bureau_tradeline_ix ON cn_core.bureau_tradeline (snapshot_id);

-- ---------------------------------------------------------------- D11 templates, D13 channel cost
ALTER TABLE cn_core.digital_template
    ADD COLUMN IF NOT EXISTS language        text,    -- ext
    ADD COLUMN IF NOT EXISTS approval_status text;    -- ext: APPROVED, PENDING, REJECTED or EXPIRED
CREATE TABLE IF NOT EXISTS cn_core.channel_cost_capacity (   -- ext
    id                bigint PRIMARY KEY,
    channel           text NOT NULL,
    agency            text NOT NULL,
    bucket            text NOT NULL,
    cost_per_attempt  numeric(10,3),
    daily_capacity    int,
    connect_rate      numeric(5,3),
    ptp_rate          numeric(5,3),
    period            text
);

-- ---------------------------------------------------------------- D10 consent and DND (borrower level)
CREATE TABLE IF NOT EXISTS compliance.consent_dnd_registry (
    registry_id        bigint PRIMARY KEY,
    customer_id        bigint NOT NULL REFERENCES cn_core.customer,
    channel            text NOT NULL,
    consent_status     text NOT NULL CHECK (consent_status IN ('GRANTED', 'NOT_GIVEN', 'REVOKED')),
    consent_ts         timestamp,            -- UTC
    opt_out_ts         timestamp,            -- UTC
    dnd_status         text NOT NULL CHECK (dnd_status IN ('REGISTERED', 'NOT_REGISTERED')),
    dnd_registered_ts  timestamp,
    consent_source     text
);
CREATE INDEX IF NOT EXISTS consent_dnd_customer_ix ON compliance.consent_dnd_registry (customer_id);

-- ---------------------------------------------------------------- D5 transcripts: language and ASR confidence
ALTER TABLE compliance.call_transcript_segment
    ADD COLUMN IF NOT EXISTS language        text,
    ADD COLUMN IF NOT EXISTS asr_confidence  numeric(4,3),
    ADD COLUMN IF NOT EXISTS end_offset_sec  numeric(8,1);

-- ---------------------------------------------------------------- D12: rules per lender
ALTER TABLE compliance.calling_policy_rule ADD COLUMN IF NOT EXISTS institution_code text;   -- null = every lender

-- the staging views filter on the dialer-qualified session key: index that expression
CREATE INDEX IF NOT EXISTS call_recording_key_ix ON compliance.call_recording ((dialer_code || ':' || call_session_id));
CREATE INDEX IF NOT EXISTS call_transcript_key_ix ON compliance.call_transcript_segment ((dialer_code || ':' || call_session_id));
CREATE INDEX IF NOT EXISTS tpicl_start_ix ON cn_core.tele_process_instance_call_logs (call_start_date_time);

-- ================================================================ the sandbox view of the book: book.d1 .. book.d13
CREATE OR REPLACE VIEW book.d1_account_master AS
SELECT a.id AS account_id, a.institution_code AS lender_id, a.customer_id AS borrower_id, a.account_number, a.product_code AS product,
       a.sanctioned_amount AS sanction_amount, a.principal_outstanding_amount AS principal_outstanding,
       a.total_outstanding_amount AS total_dues, a.installment_amount AS emi, a.tenure, a.dpd, a.delinquency_bucket_code AS bucket,
       a.disbursal_date, a.city, a.branch_code AS branch, a.restructured_flag, a.settlement_flag, a.legal_flag
FROM cn_core.account a;

CREATE OR REPLACE VIEW book.d2_borrower_master AS
SELECT c.id AS borrower_id, c.customer_name AS name,
       COALESCE((SELECT array_agg(v.variant_name ORDER BY v.id) FROM cn_core.customer_name_variant v WHERE v.customer_id = c.id), '{}') AS name_variants,
       c.birth_date AS dob,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('number', p.contact_no, 'type', p.contact_type, 'source', p.source, 'captured_date', p.captured_date) ORDER BY p.sequence_no)
                 FROM cn_core.customer_contact_number p WHERE p.customer_id = c.id), '[]') AS phones,
       COALESCE((SELECT array_agg(e.email ORDER BY e.sequence_no) FROM cn_core.customer_email e WHERE e.customer_id = c.id), '{}') AS emails,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('type', d.address_type, 'line1', d.address_line_1, 'line2', d.address_line_2, 'city', d.city, 'state', d.state, 'postal_code', d.postal_code) ORDER BY d.sequence_no)
                 FROM cn_core.customer_address d WHERE d.customer_id = c.id), '[]') AS addresses,
       c.preferred_language_code AS preferred_language, c.occupation AS occupation_type, COALESCE(c.deceased_flag, 'N') AS deceased_flag
FROM cn_core.customer c;

CREATE OR REPLACE VIEW book.d3_repayment_history AS
SELECT s.account_id, s.due_date, s.due_amount AS amount_due, s.amount_paid, s.paid_date, s.payment_mode, s.bounce_reason
FROM cn_core.account_payment_schedule s;

CREATE OR REPLACE VIEW book.d4_contact_history AS
SELECT l.dialer_code || ':' || l.call_session_id AS contact_id, b.account_id, 'CALL' AS channel, min(l.call_contact_number) AS number_or_handle,
       min(l.call_start_date_time) AS ts_source_local, min(l.dialer_code) AS source_system, NULL::text AS template_id,
       min(u.employee_code) AS agent_or_agency, (array_agg(l.call_status ORDER BY l.id DESC))[1] AS disposition, max(l.call_duration) AS duration
FROM cn_core.tele_process_instance_call_logs l
JOIN cn_core.tele_process_instance_activity b ON b.dialer_code = l.dialer_code AND b.call_session_id = l.call_session_id
LEFT JOIN uamdb.users u ON u.user_id = l.call_user_id
GROUP BY l.dialer_code, l.call_session_id, b.account_id
UNION ALL
SELECT 'MSG:' || m.id, m.account_id, m.channel, m.sms_contact_no, m.message_datetime, 'MESSAGE_LOG', m.template_id::text, 'DIGITAL', m.status, 0
FROM cn_core.communication_dashboard_t m;

CREATE OR REPLACE VIEW book.d5_call_transcripts AS
SELECT t.dialer_code || ':' || t.call_session_id AS call_id, b.account_id, t.seq AS turn_no, t.speaker, t.utterance AS text, t.language,
       t.asr_confidence, t.start_offset_sec, t.end_offset_sec, t.tag
FROM compliance.call_transcript_segment t
JOIN (SELECT DISTINCT ON (dialer_code, call_session_id) dialer_code, call_session_id, account_id
      FROM cn_core.tele_process_instance_activity ORDER BY dialer_code, call_session_id, id) b
  ON b.dialer_code = t.dialer_code AND b.call_session_id = t.call_session_id;

CREATE OR REPLACE VIEW book.d6_ptp_ledger AS
SELECT p.ptp_id, p.account_id, p.promised_date, p.promised_amount, p.channel, p.captured_by, p.status, p.amount_paid FROM cn_core.ptp_ledger p;

CREATE OR REPLACE VIEW book.d7_payment_feed AS
SELECT f.txn_id, f.account_id, f.source, f.amount, f.txn_ts AS ts, f.payer_name, f.payer_handle_masked, f.reference_text, f.status, f.reversal_flag
FROM cn_core.payment_feed f;

CREATE OR REPLACE VIEW book.d8_bank_statements AS
SELECT s.customer_id AS borrower_id, s.txn_date, s.narration, s.debit, s.credit, s.balance, s.counterparty_hint FROM cn_core.aa_bank_statement s;

CREATE OR REPLACE VIEW book.d9_bureau_snapshot AS
SELECT s.customer_id AS borrower_id, s.snapshot_month, s.bureau_score,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('lender_type', t.lender_type, 'product', t.product, 'sanctioned', t.sanctioned_amount, 'outstanding', t.outstanding_amount, 'dpd_string', t.dpd_string))
                 FROM cn_core.bureau_tradeline t WHERE t.snapshot_id = s.snapshot_id), '[]') AS tradelines,
       s.enquiries_30d, s.enquiries_90d, s.utilisation_pct AS utilisation, s.reported_phone AS bureau_phone, s.reported_address AS bureau_address
FROM cn_core.bureau_snapshot s;

CREATE OR REPLACE VIEW book.d10_consent_dnd AS
SELECT r.customer_id AS borrower_id, r.channel, r.consent_status, r.consent_ts, r.opt_out_ts, r.dnd_status, r.dnd_registered_ts, r.consent_source
FROM compliance.consent_dnd_registry r;

CREATE OR REPLACE VIEW book.d11_template_registry AS
SELECT t.template_id, t.digital_channel AS channel, t.language, t.template_body AS registered_text, t.sms_category AS category,
       t.sms_dlt_id, t.template_subject, t.approval_status
FROM cn_core.digital_template t;

CREATE OR REPLACE VIEW book.d12_policy_library AS
SELECT d.doc_id, d.title, d.doc_type, d.issuer, d.reference_no, d.effective_date, d.body AS text FROM audit.kb_document d;

CREATE OR REPLACE VIEW book.d13_channel_cost AS
SELECT c.channel, c.agency, c.bucket, c.cost_per_attempt, c.daily_capacity, c.connect_rate, c.ptp_rate, c.period FROM cn_core.channel_cost_capacity c;

GRANT USAGE ON SCHEMA book TO agent_reader, audit_team;
GRANT SELECT ON ALL TABLES IN SCHEMA book TO agent_reader, audit_team;
ALTER DEFAULT PRIVILEGES IN SCHEMA book GRANT SELECT ON TABLES TO agent_reader, audit_team;
