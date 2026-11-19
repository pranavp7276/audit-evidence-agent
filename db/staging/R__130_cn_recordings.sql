-- Recording retrieval status and transcript segments, per dialer-qualified call session.
CREATE OR REPLACE VIEW staging.recordings AS
SELECT r.recording_id::text                          AS recording_id,
       r.dialer_code || ':' || r.call_session_id     AS session_key,
       r.storage_status,
       r.recording_url,
       r.duration_sec,
       r.note,
       to_char(r.checked_at, 'YYYY-MM-DD HH24:MI:SS') AS checked_ts_src
FROM compliance.call_recording r;

CREATE OR REPLACE VIEW staging.transcript_segments AS
SELECT s.segment_id::text                            AS segment_id,
       s.dialer_code || ':' || s.call_session_id     AS session_key,
       s.seq,
       s.start_offset_sec,
       s.speaker,
       s.tag
FROM compliance.call_transcript_segment s;
