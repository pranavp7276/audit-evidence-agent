-- D5 consent registry. consent_ts carries an explicit Z, i.e. UTC.
CREATE OR REPLACE VIEW staging.d5_consents AS
SELECT
    r._row_no                       AS source_row,
    r.consent_id,
    r.account_id,
    r.channel,
    r.consent_ts                    AS consent_ts_src,
    'UTC'::text                     AS consent_ts_src_tz,
    r.consent_ts::timestamptz       AS consent_ts_utc,
    r.status,
    r.capture_source
FROM raw.d5 r;
