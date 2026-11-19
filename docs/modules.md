# Modules: how the platform is organised

The menu follows the modules an audit-management product is usually described by. The mapping started from third-party listings of Q-Aud (audit planning, forms, real-time evidence collection, exceptions and issue management, risk assessment, workflow, dashboards, alerts, PDF reports), because qaud.app itself could not be read. It is a structure to work in, not a copy of that product.

The audit plan, issue register, exceptions register, risk matrix, alerts and cross-audit dashboard were built and then taken out again as unnecessary (docs/decisions.md D-027). What remains:

| Module | Where | What it does here | Code |
|---|---|---|---|
| Conducting audits, real-time evidence collection | Audit work > Audits, New audit request | The agent reads the request, plans, retrieves, tests and investigates; the audit page shows what it is doing as it happens | `services/audit.py`, `runtime/` |
| Workflow management | The strip under each audit's title | Request read, Tested, Gaps reviewed, Letter approved; plus the five stages inside an audit | `pages/workspace.js` |
| Reports (PDF) | Audit work > Reports | Per audit: summary, lender brief, response letter, evidence pack, gap report, agent trace. PDF is the browser's save-as-PDF on a report page | `pages/reports.js`, `pages/brief.js` |
| Forms management | Forms and rules > Guardrails | The checklist of obligations an audit tests, versioned, with severity and review priority | `knowledge/guardrails.py` |
| Compliance management | Forms and rules > Compliance library, Rules & data | The circulars and policies the guardrails come from; the limits in force | `pages/kb.js`, `pages/rules.js` |
| Mobile access | Every screen | The menu becomes a strip across the top at phone width; tables scroll sideways | `style.css` |

Inside an audit, the Overview shows the acceptance criteria and the evidence traps caught, and the Findings stage holds the gap register and follow-up list.

## Rules that carry across

- A finding is never changed. Reviews and letters are separate tables.
- Fixing a gap is outside this platform (docs/problem.md).
- Every statement in a report points at a record; the letter's claims check blocks approval otherwise.
