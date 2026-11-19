-- One row per call session, qualified by dialer (session ids are only unique within a dialer).
-- cn_core.tele_process_instance_call_logs holds one row per call-status event, so a session can have several
-- (CONNECTED then DISPOSED): they are kept in `statuses` / `status_row_ids` and the call is counted once.
-- Call times are in the dialer's own zone (SlashRTC Asia/Kolkata, CognifAI UTC): see compliance.dialer_config.
-- A call mirrored in both dialers appears under each; the authoritative xref says which one counts.
-- Grouped on account_id so a lookup for one account reads only that account's sessions (the filter is pushed down).
DROP VIEW IF EXISTS staging.call_sessions CASCADE;
CREATE VIEW staging.call_sessions AS
SELECT l.dialer_code || ':' || l.call_session_id                                       AS session_key,
       l.dialer_code,
       l.call_session_id,
       b.account_id::text                                                              AS account_id,
       b.customer_id::text                                                             AS customer_id,
       acc.institution_code,
       min(l.call_contact_number)                                                      AS contact_no,
       min(l.call_direction)                                                           AS direction,
       min(tpi.process_mode)                                                           AS process_mode,
       min(l.call_user_id)                                                             AS collector_user_id,
       min(u.employee_code)                                                            AS employee_code,
       to_char(min(l.call_start_date_time), 'YYYY-MM-DD HH24:MI:SS')                   AS started_ts_src,
       min(dc.timezone)                                                                AS started_ts_src_tz,
       (min(l.call_start_date_time) AT TIME ZONE min(dc.timezone))                     AS started_ts_utc,
       (max(l.call_end_date_time) AT TIME ZONE min(dc.timezone))                       AS ended_ts_utc,
       max(l.call_duration)                                                            AS duration_sec,
       (array_agg(l.call_status ORDER BY l.id DESC))[1]                                AS final_status,
       array_agg(l.call_status ORDER BY l.id)                                          AS statuses,
       array_agg(l.id ORDER BY l.id)                                                   AS status_row_ids,
       bool_or(l.call_status = 'CONNECTED')                                            AS connected,
       (min(l.call_direction) = 'OUTBOUND' AND NOT bool_or(l.call_status = 'SYSTEM_FAILURE')) AS counts_as_attempt,
       (x.xref_id IS NOT NULL)                                                         AS is_mirror_duplicate,
       x.canonical_dialer_code || ':' || x.call_session_id                             AS mirror_of
FROM cn_core.tele_process_instance_activity b
JOIN cn_core.tele_process_instance_call_logs l ON l.dialer_code = b.dialer_code AND l.call_session_id = b.call_session_id
JOIN compliance.dialer_config dc ON dc.dialer_code = l.dialer_code
JOIN cn_core.account acc ON acc.id = b.account_id
LEFT JOIN uamdb.users u ON u.user_id = l.call_user_id
LEFT JOIN cn_core.tele_process_instance tpi ON tpi.id = l.tele_process_instance_id
LEFT JOIN compliance.call_session_xref x
       ON x.mirror_dialer_code = l.dialer_code AND x.mirror_session_id = l.call_session_id AND x.canonical_dialer_code <> l.dialer_code
GROUP BY b.account_id, b.customer_id, acc.institution_code, l.dialer_code, l.call_session_id, x.xref_id, x.canonical_dialer_code, x.call_session_id;
