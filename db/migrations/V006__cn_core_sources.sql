-- The platform now reads the CN Core replica (V005) instead of the loose CSV files. Staging views are rebuilt
-- over cn_core / uamdb / compliance (db/staging/R__1*.sql); the views over raw.* are retired. The raw.* tables
-- stay as loaded (files as provided).
DROP VIEW IF EXISTS staging.d4_contacts, staging.d5_consents, staging.d10_recordings, staging.d11_verifications,
                    staging.d12_policy, staging.notices, staging.holidays, staging.collectors, staging.certifications;

-- Every account reference in the auditor's sample, as given, and how it matched a CN account. Unmatched and
-- ambiguous references stay visible: they are not silently dropped and are not tested until resolved.
CREATE TABLE audit.sample_references (
    run_id             uuid NOT NULL REFERENCES audit.runs(run_id),
    original_ref       text NOT NULL,                    -- exactly as the auditor wrote it
    match_status       text NOT NULL CHECK (match_status IN ('matched', 'unmatched', 'ambiguous')),
    matched_account_id text,                             -- CN_CORE.ACCOUNT.ID when matched
    candidates         text[] NOT NULL DEFAULT '{}',     -- every CN account the reference could mean
    note               text,
    PRIMARY KEY (run_id, original_ref)
);
GRANT SELECT ON audit.sample_references TO agent_reader;
