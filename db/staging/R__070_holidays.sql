CREATE OR REPLACE VIEW staging.holidays AS
SELECT r._row_no AS source_row, r.holiday_date::date AS holiday_date, r.holiday_name, r.scope, r.state
FROM raw.holiday_calendar r;
