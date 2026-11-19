# Architecture

The code is a stack of six layers. **A layer may import only from layers below it.** `tests/test_architecture.py` fails the build if it does not, so the structure cannot drift back into a tangle.

```
 5  web, __main__        interface: HTTP API, browser app, command line
 4  services             use cases: run an audit, save results (the only writer), letter and evidence pack
 3  runtime              the agent: planner, orchestrator, investigator, "Ask the audit"      (never writes)
 2  checks | intake | knowledge     siblings; they do not import each other
      checks     the rules: one deterministic check per question type
      intake     request -> checks, period, sample
      knowledge  guardrails: versioned obligations, severity, priority
 1  tools                data access (read only): one registered tool per source
 0  core                 contracts, database, models (llm), clock, trace, tool registry
```

## Where a job belongs

| If you are changing... | Go to | Because |
|---|---|---|
| a shared type (`CheckSpec`, `Finding`, `Citation`) | `core/contracts.py` | every layer uses it; also change `docs/contracts.md` and add a note to `decisions.md` |
| how a source is read | `tools/<source>.py` | tools only read; they never decide a result |
| whether a call, message or notice passes | `checks/<type>.py` | judgement is code; a model never decides it |
| how a request is read, or who is sampled | `intake/` | keeps reading and sampling apart from testing |
| what is tested and how serious a failure is | `knowledge/guardrails.py` | versioned; the audit records the version applied |
| the order of work, retries, searching elsewhere | `runtime/` | the agent; returns results, does not save them |
| a second reading of gaps | `runtime/skeptic.py` (the reading), `services/challenge.py` (keeping it) | it only adds rows to `finding_challenges` |
| what kind of question something is | `intake/triage.py` | agency documents and untestable items are never evidenced |
| whether the letter's statements hold | `services/letter_lint.py` | the generator in `services/pack.py` writes the references it checks |
| saving anything to `audit.*`, the letter, the pack | `services/` | the only layer that writes |
| an API route | `web/routers/<area>.py` | one router per area |
| a screen | `web/static/js/pages/<page>.js` | one script per page |

## One audit, in code

`services/audit.py: process()` is the use case. It reads top to bottom:

1. `intake.parse_checks` and `parse_sample`: the questions, period and sample size.
2. `choose_sample`: the account references (matched, unmatched, ambiguous) or a repeatable random sample.
3. `apply_scope`: each check receives its sample, the period, and the guardrail version with its default severity and weight.
4. `store.save_checks`.
5. `runtime.run_agent`: plan, evaluate each check through its tools, investigate. Returns findings; writes nothing.
6. `store.save_findings`, then `challenge.challenge_run` (the second reading; it cannot fail the run), the report step in the trace, `store.finish_run`; the trace is saved even when the run fails.

The agent's roles and limits are in `docs/workflow.md`.

## The screens

The sidebar has three groups, matching what a person is doing:

- **Audit work**: Dashboard (every audit at a glance and what needs attention first), Audit requests, New audit request.
- **Rulebook**, read in order: 1. Knowledge base, 2. Guardrails, 3. Rules & data. Together they say what an audit is tested against. There is one copy of the rules, shared by every audit.
- **Help**: Guide; the Data explorer (advanced) sits at the bottom.

An open audit has five stages, left to right, with the pages inside each stage shown as a second row:

| Stage | Pages |
|---|---|
| Overview | Summary: where the audit stands and what to do next |
| Findings | By question · Gap register · Follow-up |
| Accounts | All accounts, then one account's file |
| Respond | Response letter · Evidence pack |
| Agent | Activity · Ask the audit |

Old links such as `#/run/<id>/gaps` still work; each page belongs to exactly one stage.
