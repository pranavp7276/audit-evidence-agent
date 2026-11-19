-- Repeatable staging scripts. Re-applied by `make staging` whenever their content changes.
-- Rules (see CONTRIBUTING.md):
--   * One file per source: R__010_d4.sql, R__020_d5.sql, ... Use CREATE OR REPLACE VIEW.
--   * Read only from raw.*; never from another team member's ad-hoc table.
--   * Every timestamp column becomes timestamptz in UTC, named <col>_utc.
--     Keep the source value as <col>_src and the assumed source zone as <col>_src_tz.
--   * Record which zone each source uses in docs/data_dictionary.md, with how you know.
--   * Carry raw._row_no through as source_row so findings can cite the exact record.
SELECT 1;
