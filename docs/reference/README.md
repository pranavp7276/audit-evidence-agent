# Real-world audit references — how they feed the agent

Four real documents from collections operations (originals go in `sources/` when the team adds them):

| Code | File | What it is |
|---|---|---|
| CHK | `Collection_Audit_Checklist.docx` | A lender's code of conduct for collection agencies: contact hours, call caps by DPD, conduct, payment channels, prohibitions |
| QM | `Quality_Monitoring_Functional_Parameters.xlsx` | Call QA scorecard: 27 parameters in 6 groups, weights, Fatal (F/NF) flags, and what speech analytics can / can't cover from a recording |
| MVA | `MONEYVIEW_AUDIT_CHECKSHEET.xlsx` | A lender's scored agency audit: 47 items in 7 groups, weights add up to 100, filled in by an agency with its own status and remarks |
| VAD | `Virtual_Audit_Document_Details.docx` | A lender's agency-level virtual audit list: 30 artefacts (contracts, licences, IT controls, premises, staff verification, recordings retention) |

The machine-readable version is **`config/check_catalog.yaml`** (29 checks). It has two companions: **`config/evidence_tags.yaml`**, which lists the fields and flags each activity type must carry so evidence exists, and **`docs/BUILD_PLAN.md`**, the build plan for Claude Code. This page explains where the rules come from.

## 1. Rules the agent should know (with the precedence that applies)

| Rule | Value in CHK | Where the agent must read it at run time |
|---|---|---|
| Calling window | 08:00–19:00 | **D12** (problem statement says hours/frequency come from D12). CHK matches the RBI 2022 circular, so use it as the fallback and note any D12 difference in the pack |
| Daily call cap | ≤30 DPD: 10/day · >30 DPD: 20/day | **D12**; fallback CHK |
| Timezone | — | Normalise every source to IST before any hour/day/date test (sources differ by design) |
| Severity | QM Fatal = any fail fails the call | **The severity scale shipped with each request** always wins; catalog `severity_hint` is fallback only |

## 2. Check catalog at a glance

| ID | Check | Evidence | Origin |
|---|---|---|---|
| HRS-01 | Calls within permitted hours | contact log, D12 | CHK, RBI |
| FRQ-01 | Daily cap by DPD bucket | contact log, DPD, D12 | CHK |
| FRQ-02 | Customer contact preferences honoured | contact log, transcripts | CHK |
| CNS-01 | Consent before WhatsApp/digital message | consent registry, template registry, contact log | Problem statement |
| TPL-01 | Every message used a template approved at send time | template registry, contact log | MVA 46–47 |
| CLI-01 | Calls only from registered numbers / dialer, no personal mobiles | contact log, D12 | MVA 15, 33, 41 |
| CNT-01 | Contacts the borrower didn't provide: no dues disclosed | contact log, transcripts | MVA 39, CHK |
| REC-01 | Recording exists for every connected call | contact log ⟂ recording store | Problem statement, QM B5 |
| REC-02 | Recording disclaimer given | transcript | QM B5 (Fatal) |
| REC-03 | Recordings retained for every month of the period | recording store vs contact log | VAD 19 |
| IDN-01 | Agent identified self + lender | transcript | CHK, QM B3/B4 |
| VER-01 | Identity verified **before** dues disclosed | transcript turn order | QM B6 + B7, CHK |
| CND-01 | No threats / abuse | transcript | CHK, QM B28 (Fatal), RBI |
| CND-02 | No false info / unauthorised promises | transcript | CHK Ethics, QM B15 (Fatal) |
| CND-03 | Payment only via authorised bank channels (no personal/agency a/c, UPI, wallet) | transcript, payments | CHK |
| CND-04 | Sensitive occasions (bereavement) | transcript | CHK |
| DSP-01 | Disposition matches the conversation | contact log vs transcript | QM B21/B22 (Fatal) |
| CRT-01 | Collector certified (DRA) on call date | cert register, roster, contact log | CHK, VAD 3/20/26, problem statement |
| CRT-02 | Police verification / RCU before deployment *(candidate)* | roster, cert register | VAD 20, MVA 27 |
| AGT-01 | Collector active (not terminated or inactive) on call date | roster, contact log | MVA 22–24, 26 |
| AGT-02 | Collector not shared with other lenders *(candidate)* | roster | MVA 16 |
| CRT-03 | Trained before calling *(candidate)* | cert register, roster | VAD 23/30 |
| NOT-01 | Notices served on time (holiday-aware) | dispatch tracker, holiday calendar | CHK, problem statement |
| NOT-02 | Agency-appointment notice before agency contact | dispatch tracker, contact log | CHK (candidate) |

## 3. Useful details from the real docs

- **VER-01 is defined by QM.** B6 says right-party confirmation is by *prefix + last name*; B7 is where dues / loan account are disclosed. So the test is turn order: `rpc_turn < first_dues_turn`. Dues told to a third party is a gap.
- **DSP-01 is something the QA team can't do.** QM marks disposition and CRM fields as "cannot be covered from the recording". The audit agent has the contact log as well, so it can cross-check the tagged disposition against the transcript.
- **Fatal items should map to the top of the request's severity scale** unless the scale says otherwise: B4, B5, B15, B16, B21, B22, B28.
- **Some CHK items have no system of record:** dress code, proximity, visit location, gifts to bank staff. If a request asks about them, mark them `cannot_determine` and say so in the letter. Never claim compliance on them.
- **Payment channel (CND-03)** is a strong transcript check to have ready. Look for UPI IDs, wallet names and "send to my account" phrasing.

## 3a. Two kinds of audit: triage each question first

VAD shows that lenders also run **agency-level** audits. These ask for artefacts such as the SOW, GST certificate, fidelity insurance, USB-blocked screenshots, CCTV retention and the BCP. None of these are in our datasets. So the request parser should first sort every question into one of three buckets:

1. **account_check**: tested per sampled account against data (`checks`).
2. **vendor_document**: an agency artefact (`vendor_document_requests`). The verdict is `cannot_determine`, and the letter lists it under *"Documents to be provided by the agency"*. 7 of the 30 VAD items partly overlap our data (recordings retention, agent register, DRA certificate, ID cards, training, cash deposits) and point to a check through `maps_to`.
3. **not_testable**: no system of record.

This stops the agent from inventing evidence when a hidden request mixes both kinds, and it keeps false "evidenced" verdicts at zero.

Notes on the source: its list runs 1–32 because item 4 wraps over two lines and there's a blank line, so there are really 30 items. The "Ok" marks next to some items look like someone's working ticks and are ignored. The doc is written for one lender's credit-card process; the catalog keeps the items lender-neutral.

## 3b. What the Moneyview sheet adds: an agency's answer is a claim, not evidence

MVA is filled in by an agency, so it shows what a real agency response looks like. Its remarks include "dialler blocks calls before 8 AM and after 7 PM" and "everything is dialled through dialler". These are claims, and an auditor tests them. Our agent should do the same:

- **Test the claim against the data.** HRS-01 and CLI-01 are still run on the contact log whatever the agency says.
- **"NA" is a claim too.** For example, "NA – no field" can be tested by querying the log for field visits. Accept it only if the data agrees.
- **Write Compliant / Gap / Cannot determine, never a bare Yes/No.** MVA#33 shows why: it answers "No" to "No calls are made through personal numbers", which can be read either way.
- **Copy the scoring format for the letter.** Items are *scorable* or *observation*, with weights adding up to 100. Use this as the fallback when a request has no severity scale.

23 of the 47 MVA items map to account-level checks through `maps_to`. The rest are agency documents, so they're treated like VAD items. The catalog doesn't copy the sheet's status and remarks columns.

## 4. Decisions still open (see `open_decisions` in the YAML)

1. Is 19:00:00 inside the window, and is the test on call start only?
2. Does the cap count attempts or connected calls?
3. Is DPD taken on the call date or at allocation?
4. When a recording is missing, the transcript-based checks for that call should be `cannot_determine`, never `evidenced`.

## 5. Not in scope for the evidence pack

QM soft-skill and negotiation items (greeting energy, CIBIL education, urgency, probing, grammar, hold or dead air). These are QA scoring, not audit compliance. They are kept in `qm_parameters` with `audit_check: null` for reference, in case a request asks about call quality.

Regulator baseline: RBI circular RBI/2022-23/108 (12 Aug 2022), *Outsourcing of Financial Services – Responsibilities of regulated entities employing Recovery Agents*. It bars calling borrowers before 08:00 or after 19:00 and bars persistent calling, intimidation, and false or misleading representations.
