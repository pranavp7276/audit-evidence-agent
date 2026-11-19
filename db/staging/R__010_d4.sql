-- D4 contact log. contact_ts is a naive local string in Asia/Kolkata (synthetic data: by design).
CREATE OR REPLACE VIEW staging.d4_contacts AS
SELECT
    r._row_no                                              AS source_row,
    r.contact_id,
    r.account_id,
    r.collector_id,
    r.channel,
    r.contact_ts                                           AS contact_ts_src,
    'Asia/Kolkata'::text                                   AS contact_ts_src_tz,
    (r.contact_ts::timestamp AT TIME ZONE 'Asia/Kolkata')  AS contact_ts_utc,
    r.outcome,
    (r.dues_disclosed = 'Y')                               AS dues_disclosed,
    r.template_id,
    r.recording_id
FROM raw.d4_contact_log r;
