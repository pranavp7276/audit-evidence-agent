-- Repeatable staging scripts. Re-applied by `make staging` whenever their content changes.
-- Rules (see CONTRIBUTING.md):
--   * One file per source: R__010_d4.sql, R__020_d5.sql, ... Use CREATE OR REPLACE VIEW.
--   * Read only from cn_core.*, compliance.* and uamdb.*; never from another team member's ad-hoc table.
--   * Every timestamp column becomes timestamptz in UTC, named <col>_utc.
--     Keep the source value as <col>_src and the assumed source zone as <col>_src_tz.
--   * Record which zone each source uses in docs/data_dictionary.md, with how you know.
--   * Carry the source key through so findings can cite the exact record (agent/tools/record_keys.py).
SELECT 1;
