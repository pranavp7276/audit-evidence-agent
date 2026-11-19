-- D11 identity verification. verified_ts carries an explicit Z, i.e. UTC.
CREATE OR REPLACE VIEW staging.d11_verifications AS
SELECT
    r._row_no                       AS source_row,
    r.verification_id,
    r.account_id,
    r.contact_id,
    r.verified_ts                   AS verified_ts_src,
    'UTC'::text                     AS verified_ts_src_tz,
    r.verified_ts::timestamptz      AS verified_ts_utc,
    r.method,
    r.result
FROM raw.d11 r;
