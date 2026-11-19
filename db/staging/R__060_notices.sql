-- Notice dispatch tracker. Dates are calendar dates in India (no time part, so no zone conversion).
CREATE OR REPLACE VIEW staging.notices AS
SELECT
    r._row_no               AS source_row,
    r.notice_id,
    r.account_id,
    r.notice_type,
    r.borrower_state,
    r.trigger_date::date    AS trigger_date,
    r.dispatch_date::date   AS dispatch_date,
    r.service_date::date    AS service_date
FROM raw.notice_dispatch r;
