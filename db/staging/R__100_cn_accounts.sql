-- Loan accounts as the auditor refers to them (ACCOUNT_NUMBER) and as CN Core keys them (ID).
-- The same account number can exist under two institutions: a reference matching more than one row is ambiguous.
CREATE OR REPLACE VIEW staging.accounts AS
SELECT a.id::text            AS account_id,
       a.account_number,
       a.institution_code,
       a.customer_id::text   AS customer_id,
       a.product_code,
       a.dpd
FROM cn_core.account a;
