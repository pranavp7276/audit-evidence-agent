-- Messages actually sent (the message log), the template's purpose, and consent history per recipient number.
DROP VIEW IF EXISTS staging.messages;
CREATE VIEW staging.messages AS
SELECT m.id::text                                                      AS message_id,
       m.account_id::text                                              AS account_id,
       m.customer_id::text                                             AS customer_id,
       m.channel,
       m.sms_contact_no                                                AS contact_no,
       to_char(m.message_datetime, 'YYYY-MM-DD HH24:MI:SS')            AS sent_ts_src,
       'Asia/Kolkata'::text                                            AS sent_ts_src_tz,
       'gateway'::text                                                 AS clock_source,
       (m.message_datetime AT TIME ZONE 'Asia/Kolkata')                AS sent_ts_utc,
       m.status,
       m.template_id,
       t.sms_category                                                  AS category,
       t.template_subject
FROM cn_core.communication_dashboard_t m
LEFT JOIN cn_core.digital_template t ON t.template_id = m.template_id
WHERE m.channel IN ('WHATSAPP', 'SMS');

DROP VIEW IF EXISTS staging.consents;
CREATE VIEW staging.consents AS
SELECT c.consent_id::text                                              AS consent_id,
       c.customer_id::text                                             AS customer_id,
       c.contact_no,
       c.channel,
       c.purpose,
       c.status,
       to_char(c.effective_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"')           AS effective_ts_src,
       'UTC'::text                                                     AS effective_ts_src_tz,
       'registry'::text                                                AS clock_source,
       (c.effective_at AT TIME ZONE 'UTC')                             AS effective_ts_utc,
       c.capture_source
FROM compliance.customer_consent c;
