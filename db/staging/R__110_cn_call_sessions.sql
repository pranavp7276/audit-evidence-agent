-- One row per call session, qualified by dialer (session ids are only unique within a dialer).
-- cn_core.tele_process_instance_call_logs holds one row per call-status event, so a session can have several
-- (CONNECTED then DISPOSED): they are kept in `statuses` / `status_row_ids` and the call is counted once.
-- Call times are in the dialer's own zone (SlashRTC Asia/Kolkata, CognifAI UTC): see compliance.dialer_config.
-- A call mirrored in both dialers appears under each; the authoritative xref says which one counts.
CREATE OR REPLACE VIEW staging.call_sessions AS
WITH bridge AS (
    SELECT DISTINCT ON (dialer_code, call_session_id) dialer_code, call_session_id, account_id, customer_id
    FROM cn_core.tele_process_instance_activity
    ORDER BY dialer_code, call_session_id, id
), logs AS (
    SELECT l.dialer_code, l.call_session_id,
           min(l.call_contact_number)                         AS contact_no,
           min(l.call_direction)                              AS direction,
           min(l.call_user_id)                                AS collector_user_id,
           min(l.tele_process_instance_id)                    AS instance_id,
           min(l.call_start_date_time)                        AS start_src,
           max(l.call_end_date_time)                          AS end_src,
           max(l.call_duration)                               AS duration_sec,
           (array_agg(l.call_status ORDER BY l.id DESC))[1]   AS final_status,
           array_agg(l.call_status ORDER BY l.id)             AS statuses,
           array_agg(l.id ORDER BY l.id)                      AS status_row_ids
    FROM cn_core.tele_process_instance_call_logs l
    GROUP BY l.dialer_code, l.call_session_id
)
SELECT g.dialer_code || ':' || g.call_session_id                                   AS session_key,
       g.dialer_code,
       g.call_session_id,
       b.account_id::text                                                          AS account_id,
       b.customer_id::text                                                         AS customer_id,
       g.contact_no,
       g.direction,
       tpi.process_mode,
       g.collector_user_id,
       u.employee_code,
       to_char(g.start_src, 'YYYY-MM-DD HH24:MI:SS')                               AS started_ts_src,
       dc.timezone                                                                 AS started_ts_src_tz,
       (g.start_src AT TIME ZONE dc.timezone)                                      AS started_ts_utc,
       (g.end_src AT TIME ZONE dc.timezone)                                        AS ended_ts_utc,
       g.duration_sec,
       g.final_status,
       g.statuses,
       g.status_row_ids,
       ('CONNECTED' = ANY (g.statuses))                                            AS connected,
       (g.direction = 'OUTBOUND' AND NOT ('SYSTEM_FAILURE' = ANY (g.statuses)))    AS counts_as_attempt,
       (x.xref_id IS NOT NULL)                                                     AS is_mirror_duplicate,
       x.canonical_dialer_code || ':' || x.call_session_id                         AS mirror_of
FROM logs g
JOIN bridge b ON b.dialer_code = g.dialer_code AND b.call_session_id = g.call_session_id
JOIN compliance.dialer_config dc ON dc.dialer_code = g.dialer_code
LEFT JOIN uamdb.users u ON u.user_id = g.collector_user_id
LEFT JOIN cn_core.tele_process_instance tpi ON tpi.id = g.instance_id
LEFT JOIN compliance.call_session_xref x
       ON x.mirror_dialer_code = g.dialer_code AND x.mirror_session_id = g.call_session_id AND x.canonical_dialer_code <> g.dialer_code;
