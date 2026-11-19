-- The audit plan and the issue register (V015) were taken out of the product. Nothing was ever recorded in them, so they are dropped.
-- Findings, reviews and everything else are untouched.
DROP TABLE IF EXISTS audit.issue_events;
DROP TABLE IF EXISTS audit.issue_findings;
DROP TABLE IF EXISTS audit.issues;
DROP TABLE IF EXISTS audit.audit_plan;
