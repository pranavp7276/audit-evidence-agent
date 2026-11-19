-- D10 recording store. recorded_ts is a naive local string in Asia/Kolkata.
CREATE OR REPLACE VIEW staging.d10_recordings AS
SELECT
    r._row_no                                              AS source_row,
    r.recording_id,
    r.contact_id,
    r.account_id,
    r.recorded_ts                                          AS recorded_ts_src,
    'Asia/Kolkata'::text                                   AS recorded_ts_src_tz,
    (r.recorded_ts::timestamp AT TIME ZONE 'Asia/Kolkata') AS recorded_ts_utc,
    r.duration_sec::int                                    AS duration_sec,
    r.storage_uri
FROM raw.d10 r;
