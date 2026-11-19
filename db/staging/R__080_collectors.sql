CREATE OR REPLACE VIEW staging.collectors AS
SELECT r._row_no AS source_row, r.collector_id, r.collector_name, r.agency, r.state, r.status
FROM raw.collector_roster r;
