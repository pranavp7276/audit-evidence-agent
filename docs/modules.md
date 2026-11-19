# Modules: how the platform is organised as an audit-management product

The menu follows the modules an audit-management product is usually described by. This mapping is built from third-party listings of Q-Aud (audit planning, forms, real-time evidence collection, exceptions and issue management, risk assessment, workflow, dashboards, alerts, PDF reports), because qaud.app itself could not be read when this was written. It is a structure to work in, not a copy of that product.

| Module | Where | What it does here | Code |
|---|---|---|---|
| Dashboard | Overview > Dashboard | How every audit stands against the acceptance criteria, what needs attention, the traps caught, and the readiness forecast | `web/routers/dashboard.py`, `pages/dashboard.js` |
| Alerts | Overview > Alerts (count in the menu) | Overdue responses, unreviewed top-severity gaps, failed audits, overdue issues and due plan entries | `registers.py: alerts`, `pages/alerts.js` |
| Audit planning, multi-year planning | Plan and conduct > Audit plan | Audits and readiness checks you expect, with owner and due date; a year view by month; recurring entries schedule the next one; Start links the audit to its entry | `services/plan.py`, `pages/plan.js` |
| Conducting audits, real-time evidence collection | Plan and conduct > Audits, New audit request | The agent reads the request, plans, retrieves, tests and investigates; the audit page shows what it is doing as it happens | `services/audit.py`, `runtime/` |
| Workflow management | The strip under each audit's title | Request read, Tested, Gaps reviewed, Letter approved; plus the five stages inside an audit | `pages/workspace.js` |
| Exceptions management | Findings and follow-up > Exceptions | Every gap and open question across audits, most serious first, with review status, second reading and issue; CSV export | `registers.py`, `pages/exceptions.js` |
| Issue management | Findings and follow-up > Issues | A confirmed gap becomes an issue with owner, due date and status; resolved needs a story, verified needs a second person; history is append-only | `services/issues.py`, `pages/issues.js` |
| Risk assessment | Findings and follow-up > Risk | Likelihood measured from the audits times impact from the request's own severity scale, on a 3 x 3 matrix | `services/risk.py`, `pages/risk.js` |
| Reports (PDF) | Findings and follow-up > Reports | Per audit: summary, lender brief, response letter, evidence pack, gap report, agent trace; across audits: exceptions and issue registers. PDF is the browser's save-as-PDF on a report page | `pages/reports.js`, `pages/brief.js` |
| Forms management | Forms and rules > Guardrails | The checklist of obligations an audit tests, versioned, with severity and review priority | `knowledge/guardrails.py` |
| Compliance management | Forms and rules > Compliance library, Rules & data | The circulars and policies the guardrails come from; the limits in force | `pages/kb.js`, `pages/rules.js` |
| Mobile access | Every screen | The menu becomes a strip across the top at phone width; tables scroll sideways | `style.css` |

## Rules that carry across the modules

- A finding is never changed. Exceptions, issues, risk and reports read findings; reviews, issues and plan entries are separate tables.
- Fixing a gap is outside this platform (docs/problem.md). An issue records who owns it, when it is due, how it was resolved and who verified it.
- Every statement in a report points at a record; the letter's claims check blocks approval otherwise.
