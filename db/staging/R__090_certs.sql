-- Certification register. Dates are inclusive on both ends (proposed, docs/decisions.md D-010).
CREATE OR REPLACE VIEW staging.certifications AS
SELECT r._row_no AS source_row, r.cert_id, r.collector_id, r.cert_name,
       r.valid_from::date AS valid_from, r.valid_to::date AS valid_to
FROM raw.cert_register r;
