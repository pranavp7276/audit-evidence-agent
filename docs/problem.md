# Problem statement: Audit evidence pack agent

## Business context
Lenders audit their outsourced collections regularly, and regulators inspect them. A typical request samples a few hundred accounts and asks for proof: consent before each WhatsApp message, calls within permitted hours and frequency, identity verified before dues were disclosed, notices served on time, recovery agents certified on the day they called. Analysts spend weeks pulling this from contact logs, recordings, consent records and notice trackers, and the auditor often finds the gaps first.

## Objective
Answer any audit request with a complete evidence pack within a day, and report every gap before the auditor finds it.

## Users
Compliance; internal audit; lender relationship managers.

## Scope
**In:** reading the request, turning questions into checks, retrieving and testing evidence per sampled account, gap report, draft response.
**Out:** fixing gaps, preventing breaches before dispatch (CO-02).

## Why agentic
Every request is worded differently and asks for evidence spread across systems. The agent turns questions into checks, decides where to look, and judges whether what it found proves the point: a consent record dated after the message does not. Then it writes a response that states gaps plainly. A fixed report answers last year's audit, not this one.

## What makes it hard
Questions are vague or bundle several checks. Evidence exists but is subtly wrong: consent captured after the first message, time zones that differ between systems, one recording missing from a series of calls. The pack must never claim compliance it cannot prove.

## Functional requirements
1. Read an audit request (PDF or email text) and split it into checks, each with its sample and test.
2. Map each check to sources: D4, D5, D10, D11, D12, the notice dispatch history and the certification register. Calling hours and frequency limits come from D12.
3. Retrieve and test evidence per sampled account: consent before contact, hours and frequency, verification before disclosure, notice timelines, agent certification on the call date.
4. Mark each check per account as evidenced, gap or cannot determine, citing records.
5. Produce the evidence pack (index, extracts, record references) and a gap report graded on the provided severity scale.
6. Draft the response letter for compliance review.

## Non-functional requirements
A 300-account, 10-question request completed in under 2 hours. Every statement in the pack traceable to a record.

## Data provided
| Dataset | Volume | Notes |
|---|---|---|
| Audit requests (CO-04 only) | 3 public, 5 hidden | PDF and email text; vague and compound questions; each comes with a severity scale; gap keys for the public requests |
| D4, D5, D10, D11, D12 | full | late consent and missing recordings seeded; time zones differ between some sources by design |
| Notice dispatch history (CO-04 only) | notices sent in the last 12 months | dispatch and service dates; late service seeded |
| Holiday calendar | national and state, 2026–27 | for notice timelines |
| Collector roster and certification register | about 1,200 collectors | IDs match D4; some certificates expired before calls the collector made |
| Ground truth (hidden) | 5 requests | true gaps per account and check |

## Tools the agent must call
Warehouse SQL, contact log, transcript and recording store, consent registry, template registry, dispatch tracker, certification register.

## Guardrails
No compliance claim without a cited record. Gaps are reported as found, never dropped or softened. Borrower data in the pack is limited to what the request needs.

## Acceptance criteria
On the hidden requests: gap recall of 95%, false gaps under 5%, and zero compliance claims without evidence.
