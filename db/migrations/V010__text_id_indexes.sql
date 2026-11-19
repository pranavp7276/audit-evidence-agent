-- The staging views expose ids as text (account_id::text). A filter on that text value cannot use a plain bigint index, so index the same
-- expression: per-account lookups stay fast as the book grows.
CREATE INDEX IF NOT EXISTS comm_dash_acc_txt_ix ON cn_core.communication_dashboard_t ((account_id::text));
CREATE INDEX IF NOT EXISTS teia_account_txt_ix  ON cn_core.tele_process_instance_activity ((account_id::text));
CREATE INDEX IF NOT EXISTS notice_account_txt_ix ON compliance.notice ((account_id::text));
CREATE INDEX IF NOT EXISTS account_id_txt_ix    ON cn_core.account ((id::text));
CREATE INDEX IF NOT EXISTS account_number_up_ix ON cn_core.account ((upper(account_number)));
CREATE INDEX IF NOT EXISTS customer_id_txt_ix   ON cn_core.customer ((id::text));
