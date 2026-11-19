-- CN Core replica for audit testing: the collections tables the audit reads, with the real CN_CORE / UAMDB
-- table and column names (Oracle NUMBER -> bigint/numeric, VARCHAR2 -> text, DATE/TIMESTAMP -> timestamp).
-- Only the columns the audit needs are present; the full tables have many more. Source: CN_CORE and UAMDB
-- DDL exports and the telecalling data model.
--
--   uamdb        identity: organisations, users, roles                       (real structure)
--   cn_core      customers, accounts, cases, contact numbers, activity log,
--                tele-calling process / call logs, message log, templates    (real structure)
--   compliance   data the audit needs that CN Core does not hold: consent, certification, D12 rules,
--                holidays, recordings, transcripts, notice dispatch, dialer config (NOT in the supplied DDL;
--                designed here in the same style. See docs/cn_core_model.md for what is assumed.)
--
-- Columns marked "-- ext" are additions to a real CN Core table (dialer code, template link) that the supplied
-- DDL does not have; they exist so SlashRTC and CognifAI calls can be told apart and messages tied to a template.

CREATE SCHEMA IF NOT EXISTS uamdb;
CREATE SCHEMA IF NOT EXISTS cn_core;
CREATE SCHEMA IF NOT EXISTS compliance;

-- ================================================================ UAMDB ================================================================
CREATE TABLE uamdb.organization_type (
    organization_type_id       bigint PRIMARY KEY,
    organization_type_code     text NOT NULL,
    organization_type_name     text,
    organization_type_category text,
    authentication_type        text,
    two_factor_auth            char(1),
    organization_type_desc     text
);
CREATE TABLE uamdb.organization (
    organization_id            bigint PRIMARY KEY,
    organization_code          text NOT NULL,
    organization_name          text NOT NULL,
    organization_type_id       bigint NOT NULL REFERENCES uamdb.organization_type,
    registered_address         text,
    registered_contact_no      text,
    organization_email         text,
    city                       text,
    state                      text,
    postal_code                text,
    country                    text,
    contact_person_name        text,
    contact_person_designation text,
    contact_person_contact_no  text,
    organization_status        text
);
CREATE TABLE uamdb.roles (
    role_id               bigint PRIMARY KEY,
    role_name             text NOT NULL,
    role_description      text,
    organization_id       bigint REFERENCES uamdb.organization,
    role_type             text,
    parent_role_id        bigint,
    admin_role_flag       char(1),
    super_admin_role_flag char(1)
);
CREATE TABLE uamdb.users (
    user_id              bigint PRIMARY KEY,
    user_name            text NOT NULL UNIQUE,
    organization_id      bigint NOT NULL REFERENCES uamdb.organization,
    first_name           text,
    middle_name          text,
    last_name            text,
    role_id              bigint REFERENCES uamdb.roles,
    designation          text,
    department           text,
    employee_code        text,              -- the collector id used by the contact log and the certification register
    reporting_manager_id bigint,
    base_branch_code     text,
    contact_no           text,
    email                text,
    city                 text,
    state                text,
    postal_code          text,
    country              text,
    gender               text,
    preferred_language   text,
    user_status          text
);
CREATE TABLE uamdb.user_role_link (
    user_role_link_id bigint PRIMARY KEY,
    user_id           bigint NOT NULL REFERENCES uamdb.users,
    role_id           bigint NOT NULL REFERENCES uamdb.roles
);

-- ================================================================ CN_CORE: customer and account ================================================================
CREATE TABLE cn_core.customer (
    id                        bigint PRIMARY KEY,
    institution_code          text NOT NULL,
    source_system_code        text,
    customer_number           text NOT NULL,
    unified_customer_id       text,
    customer_name             text,
    customer_first_name       text,
    customer_last_name        text,
    father_name               text,
    customer_status_id        int,
    gender_code               text,
    customer_category_code    char(1),
    customer_type_code        text,
    branch_code               text,
    occupation                text,
    preferred_language_code   text,
    open_date                 date,
    birth_date                date
);
CREATE INDEX customer_number_ix ON cn_core.customer (institution_code, customer_number);

CREATE TABLE cn_core.customer_contact_number (
    id                    bigint PRIMARY KEY,
    customer_id           bigint NOT NULL REFERENCES cn_core.customer,
    category              text,
    sequence_no           int,
    contact_type          text,
    contact_no            text NOT NULL,
    contact_number_type   text,
    std_code              text,
    isd_code              text,
    contact_name          text,
    verified_status       text
);
CREATE INDEX customer_contact_number_cust_ix ON cn_core.customer_contact_number (customer_id);
CREATE INDEX customer_contact_number_no_ix ON cn_core.customer_contact_number (contact_no);

CREATE TABLE cn_core.account (
    id                               bigint PRIMARY KEY,
    institution_code                 text NOT NULL,
    source_system_code               text,
    account_number                   text NOT NULL,
    account_type_code                text,
    customer_id                      bigint NOT NULL REFERENCES cn_core.customer,
    branch_code                      text,
    product_category_code            text,
    product_segment_code             text,
    product_group_code               text,
    product_code                     text,
    account_status_id                int,
    loan_amount                      numeric(21,3),
    sanctioned_amount                numeric(21,3),
    disbursed_amount                 numeric(21,3),
    open_date                        date,
    disbursal_date                   date,
    maturity_date                    date,
    close_date                       date,
    tenure                           int,
    interest_rate                    numeric(9,5),
    installment_amount               numeric(21,3),
    repayment_cycle_day              int,
    due_date                         date,
    next_due_date                    date,
    principal_outstanding_amount     numeric(21,3),
    interest_outstanding_amount      numeric(21,3),
    total_outstanding_amount         numeric(21,3),
    total_overdue_amount             numeric(21,3),
    dpd                              int,
    delinquency_bucket_code          text,
    last_payment_received_date       timestamp,
    last_payment_received_amount     numeric(21,3),
    npa_flag                         char(1),
    overdue_since_date               date
);
CREATE INDEX account_number_ix ON cn_core.account (account_number);
CREATE INDEX account_customer_ix ON cn_core.account (customer_id);

CREATE TABLE cn_core.account_customer_contact_number (
    id                  bigint PRIMARY KEY,
    account_id          bigint NOT NULL REFERENCES cn_core.account,
    customer_id         bigint NOT NULL REFERENCES cn_core.customer,
    category            text,
    sequence_no         int,
    contact_type        text,
    contact_no          text NOT NULL,
    contact_number_type text,
    std_code            text,
    isd_code            text,
    contact_name        text
);
CREATE INDEX acc_cust_contact_acc_ix ON cn_core.account_customer_contact_number (account_id);

CREATE TABLE cn_core.collection_case (
    id                                  bigint PRIMARY KEY,
    case_year                           int,
    case_month                          int,
    case_start_date                     timestamp,
    case_end_date                       timestamp,
    case_status_id                      int,
    collection_status                   text,
    resolution_status                   text,
    account_id                          bigint NOT NULL REFERENCES cn_core.account,
    case_owner_user_id                  bigint,
    allocated_collection_user_id        bigint,
    allocated_collection_agency_id      bigint,
    allocated_tele_call_user_id         bigint,
    allocated_tele_call_agency_id       bigint,
    allocated_tele_call_agency_user_id  bigint,
    case_start_dpd                      int,
    dpd                                 int,
    delinquency_bucket_code             text,
    total_outstanding_amount            numeric(21,3)
);
CREATE INDEX collection_case_acc_ix ON cn_core.collection_case (account_id);

-- ================================================================ CN_CORE: disposition masters ================================================================
CREATE TABLE cn_core.disposition_group (
    disposition_group_code text PRIMARY KEY,
    disposition_group_name text
);
CREATE TABLE cn_core.disposition_code (
    disposition_code           text PRIMARY KEY,
    disposition_code_name      text,
    disposition_group_code     text,
    disposition_level          char(1),
    sub_disposition_label_name text
);

-- ================================================================ CN_CORE: telecalling ================================================================
CREATE TABLE cn_core.tele_campaign (
    id                 bigint PRIMARY KEY,
    tele_campaign_name text,
    campaign_owner_id  bigint,
    campaign_status    char(1),
    created_date       timestamp
);
CREATE TABLE cn_core.tele_process_type (
    id                        bigint PRIMARY KEY,
    process_type_name         text,
    process_type_mode         text,          -- MANUAL or CAMPAIGN
    campaign_id               bigint,
    process_type_status       text,
    calling_ratio             int,
    dialer_process_id         bigint,
    wait_time                 int,
    times_to_try              int,
    sticky_agent_flag         int,
    inbound_delay_time        int,
    process_call_attempts     int,
    process_max_calls_per_day int,
    created_date              date,
    dialer_code               text           -- ext: SLASHRTC or COGNIFAI
);
CREATE TABLE cn_core.tele_process_instance (
    id                  bigint PRIMARY KEY,
    process_type_id     bigint NOT NULL REFERENCES cn_core.tele_process_type,
    process_name        text,
    process_mode        text,
    campaign_id         bigint,
    process_status      text,
    calling_ratio       int,
    dialer_process_id   bigint,
    process_start_date  date,
    process_start_time  timestamp,
    process_end_date    date,
    process_end_time    timestamp,
    number_of_accounts  int,
    number_of_agents    int,
    supervisor_id       bigint,
    dialer_code         text                 -- ext
);
CREATE TABLE cn_core.tele_process_instance_user_link (
    id                       bigint PRIMARY KEY,
    tele_process_instance_id bigint NOT NULL REFERENCES cn_core.tele_process_instance,
    user_id                  bigint NOT NULL REFERENCES uamdb.users,
    user_group_id            bigint
);
-- One row per call-status event of a call attempt: a session can have several (e.g. CONNECTED then DISPOSED).
CREATE TABLE cn_core.tele_process_instance_call_logs (
    id                       bigint PRIMARY KEY,
    tele_process_instance_id bigint REFERENCES cn_core.tele_process_instance,
    call_contact_number      text,
    user_contact_number      text,
    call_direction           text,
    call_status              text,
    call_session_id          text NOT NULL,
    call_start_date_time     timestamp,      -- in the dialer's own time zone (compliance.dialer_config)
    call_end_date_time       timestamp,
    call_duration            int,
    call_recording_link      text,
    call_user_id             bigint REFERENCES uamdb.users,
    dialer_code              text NOT NULL   -- ext
);
CREATE INDEX tpicl_session_ix ON cn_core.tele_process_instance_call_logs (dialer_code, call_session_id);
CREATE INDEX tpicl_contact_ix ON cn_core.tele_process_instance_call_logs (call_contact_number);

CREATE TABLE cn_core.tele_process_instance_activity (   -- bridges a call session to the account and the activity it produced
    id                       bigint PRIMARY KEY,
    tele_process_instance_id bigint REFERENCES cn_core.tele_process_instance,
    account_id               bigint NOT NULL REFERENCES cn_core.account,
    customer_id              bigint NOT NULL REFERENCES cn_core.customer,
    call_session_id          text NOT NULL,
    call_log_id              bigint,
    activity_status          text,
    activity_log_id          bigint,
    dialer_code              text NOT NULL        -- ext
);
CREATE INDEX teia_session_ix ON cn_core.tele_process_instance_activity (dialer_code, call_session_id);
CREATE INDEX teia_account_ix ON cn_core.tele_process_instance_activity (account_id);

-- ================================================================ CN_CORE: activity log ================================================================
CREATE TABLE cn_core.activity_log (
    id                                     bigint PRIMARY KEY,
    customer_id                            bigint,
    account_id                             bigint,
    activity_level                         char(1),
    activity_type_code                     text,
    activity_sub_type_code                 text,
    activity_code                          text,
    target_party_type_code                 text,
    target_party_customer_id               bigint,
    target_party_contact_number_category   text,
    target_party_contact_number_id         bigint,
    target_party_other_contact_number      text,
    activity_datetime                      timestamp,   -- set by CN Core to Asia/Calcutta at insert (TRG_SET_ACTIVITYDATE)
    target_party_contacted_status          char(1),
    contacted_party_name                   text,
    contacted_party_relation               text,
    contacted_party_contact_number         text,
    disposition_group_code                 text,
    disposition_code                       text,
    disposition_sub_code                   text,
    next_activity_code                     text,
    next_activity_datetime                 timestamp,
    ptp_amount                             numeric(21,3),
    ptp_payment_mode                       text,
    user_remarks                           text,
    party_interaction_status               text,
    activity_detail                        text,
    created_date                           timestamp,
    created_by                             bigint,
    creation_mode                          text,
    activity_done_by                       bigint,
    source_system_code                     text,        -- SLASHRTC or COGNIFAI for calls
    external_disposition_code              text,
    call_start_datetime                    timestamp,
    call_end_datetime                      timestamp,
    call_recording_url                     text,
    call_status                            text
);
CREATE INDEX activity_log_acc_ix ON cn_core.activity_log (account_id);
CREATE INDEX activity_log_done_by_ix ON cn_core.activity_log (activity_done_by);

-- ================================================================ CN_CORE: messages and templates ================================================================
CREATE TABLE cn_core.digital_template (
    template_id      bigint PRIMARY KEY,
    sms_category     text,                 -- SERVICE, COLLECTIONS or PROMOTIONAL: the purpose a recipient must have consented to
    sms_dlt_id       text,
    digital_channel  text,
    template_subject text,
    template_body    text
);
CREATE TABLE cn_core.communication_dashboard_t (   -- the message log: one row per message sent
    id                          bigint PRIMARY KEY,
    account_id                  bigint,
    account_number              text,
    message_datetime            timestamp,         -- Asia/Kolkata
    channel                     text,              -- WHATSAPP, SMS or EMAIL
    rule_name                   text,
    message_status              text,
    customer_id                 bigint,
    customer_name               text,
    message_type                text,
    language                    text,
    sms_contact_no              text,              -- the recipient number
    sms_final_message           text,
    status                      text,
    delivery_status             text,
    delivery_datetime           timestamp,
    template_id                 bigint REFERENCES cn_core.digital_template   -- ext
);
CREATE INDEX comm_dash_acc_ix ON cn_core.communication_dashboard_t (account_id);

-- ================================================================ CN_CORE: notices ================================================================
CREATE TABLE cn_core.notice_document (
    id                  bigint PRIMARY KEY,
    notice_id           bigint NOT NULL,
    document_version_no int,
    is_latest_version   int,
    document_link       text,
    document_date       timestamp,
    notice_reference_no text
);

-- ================================================================ COMPLIANCE: what CN Core does not hold ================================================================
CREATE TABLE compliance.dialer_config (
    dialer_code   text PRIMARY KEY,
    dialer_name   text NOT NULL,
    timezone      text NOT NULL,            -- the time zone of the dialer's call timestamps
    session_id_format text
);
-- A call mirrored across dialers appears once under each; this is the authoritative cross-reference.
CREATE TABLE compliance.call_session_xref (
    xref_id            bigint PRIMARY KEY,
    dialer_code        text NOT NULL,
    call_session_id    text NOT NULL,
    mirror_dialer_code text NOT NULL,
    mirror_session_id  text NOT NULL,
    relation           text NOT NULL DEFAULT 'MIRROR',
    canonical_dialer_code text NOT NULL     -- the dialer whose record counts
);
CREATE TABLE compliance.calling_policy_rule (   -- D12: effective-dated calling rules
    rule_id        bigint PRIMARY KEY,
    policy_code    text NOT NULL DEFAULT 'D12',
    rule_key       text NOT NULL,
    rule_value     text NOT NULL,
    unit           text,
    counting_unit  text,
    counting_rule  text,
    effective_from date NOT NULL,
    effective_to   date,                    -- exclusive; null = still in force
    note           text
);
CREATE TABLE compliance.holiday_calendar (
    holiday_id   bigint PRIMARY KEY,
    holiday_date date NOT NULL,
    holiday_name text,
    scope        text NOT NULL,
    state        text
);
CREATE TABLE compliance.customer_consent (     -- consent history per recipient number, channel and purpose
    consent_id   bigint PRIMARY KEY,
    customer_id  bigint NOT NULL REFERENCES cn_core.customer,
    contact_no   text NOT NULL,
    channel      text NOT NULL,
    purpose      text NOT NULL,
    status       text NOT NULL CHECK (status IN ('GRANTED', 'REVOKED')),
    effective_at timestamp NOT NULL,         -- UTC
    capture_source text
);
CREATE INDEX customer_consent_no_ix ON compliance.customer_consent (contact_no, channel);
CREATE TABLE compliance.collector_certification (   -- keyed by the collector's employee code, as the register is
    cert_id         bigint PRIMARY KEY,
    employee_code   text NOT NULL,
    certification   text NOT NULL,
    certificate_no  text,
    valid_from      date NOT NULL,
    valid_to        date NOT NULL,
    issuer          text
);
CREATE INDEX collector_cert_emp_ix ON compliance.collector_certification (employee_code);
CREATE TABLE compliance.call_recording (       -- retrieval status of each call's recording from the recording store
    recording_id    bigint PRIMARY KEY,
    dialer_code     text NOT NULL,
    call_session_id text NOT NULL,
    recording_url   text,
    duration_sec    int,
    storage_status  text NOT NULL CHECK (storage_status IN ('AVAILABLE', 'NOT_FOUND', 'RETRIEVAL_FAILED')),
    checked_at      timestamp,
    note            text
);
CREATE INDEX call_recording_session_ix ON compliance.call_recording (dialer_code, call_session_id);
CREATE TABLE compliance.call_transcript_segment (   -- transcript with timestamps as offsets into the recording
    segment_id      bigint PRIMARY KEY,
    dialer_code     text NOT NULL,
    call_session_id text NOT NULL,
    seq             int NOT NULL,
    start_offset_sec numeric(8,1) NOT NULL,
    speaker         text NOT NULL,
    utterance       text,
    tag             text                    -- IDENTITY_CHECK_REQUEST, IDENTITY_CHECK_PASS, IDENTITY_CHECK_FAIL, DUES_DISCLOSURE, UNCLEAR, NONE
);
CREATE INDEX call_transcript_session_ix ON compliance.call_transcript_segment (dialer_code, call_session_id, seq);
CREATE TABLE compliance.notice (               -- legal / demand notices: trigger, dispatch and service
    notice_id       bigint PRIMARY KEY,
    account_id      bigint NOT NULL REFERENCES cn_core.account,
    notice_type     text NOT NULL,
    trigger_event   text,
    trigger_date    date NOT NULL,
    dispatch_date   date,
    served_date     date,
    dispatch_mode   text,
    borrower_state  text
);
CREATE INDEX notice_account_ix ON compliance.notice (account_id);

GRANT USAGE ON SCHEMA uamdb, cn_core, compliance TO agent_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA uamdb, cn_core, compliance TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA uamdb GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA cn_core GRANT SELECT ON TABLES TO agent_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA compliance GRANT SELECT ON TABLES TO agent_reader;
