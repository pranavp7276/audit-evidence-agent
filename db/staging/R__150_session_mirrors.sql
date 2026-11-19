-- For a call session, the sessions the other dialer logged for the same call (authoritative cross-reference).
-- The investigator uses it to look for a recording or transcript held under the mirrored session.
CREATE OR REPLACE VIEW staging.session_mirrors AS
SELECT x.dialer_code || ':' || x.call_session_id               AS session_key,
       x.mirror_dialer_code || ':' || x.mirror_session_id      AS mirror_key,
       x.canonical_dialer_code || ':' || x.call_session_id     AS canonical_key
FROM compliance.call_session_xref x;
