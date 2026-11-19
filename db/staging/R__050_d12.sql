-- D12 policy limits: one row per parameter. Values stay text; consumers cast what they read.
CREATE OR REPLACE VIEW staging.d12_policy AS
SELECT r._row_no AS source_row, r.policy_key, r.policy_value, r.unit, r.applies_to, r.note
FROM raw.d12 r;
