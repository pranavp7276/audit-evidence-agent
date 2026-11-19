-- What the agent did on a run: its plan, each retrieval and evaluation step, and every investigation (an alternative source tried, a
-- retry, a finding left for review). The trace explains a result; it never decides one (pass or fail is in agent/checks).
CREATE TABLE audit.agent_steps (
    step_id     bigserial PRIMARY KEY,
    run_id      uuid NOT NULL REFERENCES audit.runs(run_id),
    seq         int  NOT NULL,
    phase       text NOT NULL CHECK (phase IN ('plan', 'retrieve', 'evaluate', 'investigate', 'report')),
    agent       text NOT NULL,                  -- planner, retriever, evaluator, investigator, reporter
    action      text NOT NULL,                  -- a plain sentence: what was done and why
    tool        text,                           -- the tool called, if any
    check_id    text,
    account_id  text,
    status      text NOT NULL CHECK (status IN ('ok', 'retry', 'resolved', 'unresolved', 'failed', 'info')),
    detail      jsonb NOT NULL DEFAULT '{}',
    duration_ms int,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, seq)
);
CREATE INDEX agent_steps_run_ix ON audit.agent_steps (run_id, seq);
GRANT SELECT ON audit.agent_steps TO agent_reader;
