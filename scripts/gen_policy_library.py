"""D12 policy library: about 200 synthetic documents (fair-practice circulars, lender policies, delegation grids, calling-hours and
contact-frequency caps, SOPs) loaded into the knowledge base (audit.kb_document / kb_clause).

The calling-hours and contact-frequency documents of each lender state the same numbers as that lender's structured D12 rules in
compliance.calling_policy_rule (see scripts/gen_book.py), including the dated changes, so the library and the rules agree.
Regulator circulars state the outer limits; lenders are the same or stricter.
"""
from __future__ import annotations

import random
from datetime import date

from agent.guardrails import split_clauses

SEED_USER = "book-seed"  # documents added by this script carry this name so a reload can replace them

LENDERS = {
    "BANK01": {"name": "Sahyadri Bank", "type": "bank",
               "hours": [(date(2025, 1, 1), "8:00 a.m.", "7:00 p.m."), (date(2026, 4, 1), "8:00 a.m.", "6:50 p.m.")],
               "cap": [(date(2025, 1, 1), "four"), (date(2026, 6, 1), "five")]},
    "NBFC01": {"name": "Kaveri Finserv", "type": "NBFC", "hours": [(date(2025, 1, 1), "8:00 a.m.", "7:00 p.m.")], "cap": [(date(2025, 1, 1), "three")]},
    "MFI01": {"name": "Ganga Microfinance", "type": "MFI", "hours": [(date(2025, 1, 1), "9:00 a.m.", "6:00 p.m.")], "cap": [(date(2025, 1, 1), "two")]},
}
LEVELS = [("L1 Collection Officer", "25,000"), ("L2 Team Lead", "75,000"), ("L3 Regional Manager", "2,50,000"), ("L4 Head of Collections", "10,00,000"), ("L5 Credit Committee", "above 10,00,000")]


def _regulator(topic: str, rnd: random.Random) -> list[str]:
    pool = {
        "calling hours": ["Recovery calls to borrowers shall be made only between 8:00 a.m. and 7:00 p.m. local time.", "No call shall be made outside these hours except at the borrower's written request.",
                          "The regulated entity shall ensure outsourced agencies follow the same hours."],
        "contact frequency": ["Not more than five attempts per day shall be made to the same contact number.", "Repeated calls intended to harass the borrower are prohibited.",
                              "The entity shall maintain a record of every attempt, with date, time and outcome."],
        "consent and channels": ["Prior consent is required before sending any WhatsApp or SMS message for collections.", "A borrower may withdraw consent at any time, and messages shall stop from that moment.",
                                 "Promotional messages shall not be sent under a collections consent."],
        "identity verification": ["The borrower's identity must be verified before any dues or loan details are disclosed on a call.", "Details shall not be shared with third parties.",
                                  "Where verification fails, no account information shall be disclosed."],
        "notices": ["Demand notices shall be dispatched within three working days of the default trigger.", "Notices shall be served within seven working days of the trigger.",
                    "Proof of dispatch and service shall be retained."],
        "agent conduct": ["Recovery agents must be certified, and the certification must be valid on the date of every call.", "Agents shall carry identification and shall not use abusive language.",
                          "The entity shall train agents annually."],
        "recording and retention": ["All collection calls shall be recorded and recordings retained for twelve months.", "Recordings shall be made available to the auditor on request.",
                                    "A missing recording shall be reported as an exception."],
        "grievance redressal": ["A borrower complaint shall be acknowledged within two working days.", "The entity shall resolve complaints within thirty days.", "Escalation shall be to the nodal officer."],
    }
    return pool[topic]


def _lender_policy(code: str, topic: str, version: int, rnd: random.Random) -> list[str]:
    L = LENDERS[code]
    n = L["name"]
    hours = L["hours"][min(version - 1, len(L["hours"]) - 1)]
    cap = L["cap"][min(version - 1, len(L["cap"]) - 1)]
    pool = {
        "calling hours policy": [f"{n} permits collection calls only between {hours[1]} and {hours[2]} local time.", "Agencies shall configure their dialers so that no call starts outside this window.",
                                 "Dialer timestamps shall be recorded with their time zone."],
        "contact frequency policy": [f"{n} limits attempts to {cap[1]} per day to the same contact number, across all dialers and modes.", "A call recorded by two dialers counts as one attempt.",
                                     "System failures are not counted as attempts."],
        "consent management policy": [f"{n} sends collections messages only to numbers with recorded consent for that purpose.", "Consent is held per number, per channel and per purpose.",
                                      "Withdrawal of consent takes effect immediately."],
        "identity verification standard": [f"On every call, {n} agents verify the borrower's date of birth before disclosing any amount.", "A failed verification ends the disclosure.",
                                           "The recording is the evidence of verification."],
        "notice management policy": [f"{n} dispatches demand notices within three working days and serves them within seven working days of the trigger.", "Holidays are excluded from the count.",
                                     "Dispatch and service dates are recorded in the notice tracker."],
        "agency code of conduct": [f"Agencies working for {n} shall use only certified recovery agents.", "Agents shall not contact borrowers at their workplace without consent.",
                                   "Breach of this code may end the agency's mandate."],
        "recording and retention policy": [f"{n} records every collection call and retains recordings for twelve months.", "Retrieval failures shall be logged and re-tried within one working day.",
                                           "Missing recordings are reported to Compliance."],
        "escalation matrix": ["Complaints on conduct are escalated to the agency head within one working day.", "Repeated breaches are escalated to the Head of Collections.",
                              "Regulatory breaches are reported to the Compliance Officer immediately."],
        "outsourcing policy": [f"{n} remains responsible for the conduct of its outsourced agencies.", "Agencies shall be audited at least once a year.", "Sub-contracting requires written approval."],
        "vulnerable borrower handling": ["Borrowers who are ill, bereaved or deceased shall not be contacted for collections.", "Such cases shall be flagged and referred to the case owner.",
                                         "Contact resumes only on written clearance."],
        "language policy": ["Calls shall be made in the borrower's preferred language where an agent is available.", "Scripts are approved in Hindi, English, Kannada, Tamil and Telugu.", "Code-mixed speech is acceptable."],
        "settlement policy": ["Settlements require approval as per the delegation grid.", "A settlement letter shall be issued before any payment is accepted.", "Waivers are recorded against the account."],
    }
    return pool[topic]


def _delegation(code: str, rnd: random.Random) -> list[str]:
    n = LENDERS[code]["name"]
    out = [f"This grid applies to settlements and waivers at {n}."]
    for i, (lvl, lim) in enumerate(LEVELS, 1):
        out.append(f"Authority {i}: {lvl} may approve settlements up to Rs {lim}.")
    return out


def _sop(topic: str, rnd: random.Random) -> list[str]:
    pool = {
        "pre-call identity verification": ["Ask the borrower to state their date of birth.", "Compare it with the account record.", "Disclose dues only after a successful match."],
        "WhatsApp template usage": ["Use only approved templates.", "Check consent for the number before sending.", "Do not use promotional templates for collections."],
        "recording retention": ["Store every recording against its dialer session id.", "Verify the upload within one working day.", "Report any session with no recording."],
        "notice dispatch": ["Generate the notice on the trigger date.", "Dispatch within three working days.", "Record the service date when proof is received."],
        "agent certification renewal": ["Track certificate expiry monthly.", "Remove agents from dialing before their certificate lapses.", "Record the new certificate on renewal."],
        "calling window configuration": ["Set the dialer window to the lender's policy.", "Review after every policy change.", "Keep a screenshot of the configuration."],
        "attempt counting": ["Count each outbound session once.", "Do not count system failures.", "Reconcile mirrored sessions across dialers daily."],
        "consent capture": ["Capture consent with the channel and purpose.", "Store the time in UTC.", "Record withdrawals the same day."],
    }
    return pool[topic]


def build_documents(rnd: random.Random) -> list[dict]:
    docs: list[dict] = []

    def add(title, doc_type, issuer, ref, eff, clauses):
        docs.append({"title": title, "doc_type": doc_type, "issuer": issuer, "reference_no": ref, "effective_date": eff,
                     "body": "\n\n".join(f"{i}. {c}" for i, c in enumerate(clauses, 1))})
    topics = ["calling hours", "contact frequency", "consent and channels", "identity verification", "notices", "agent conduct", "recording and retention", "grievance redressal"]
    k = 0
    for year, months in ((2024, (2, 5, 9, 12)), (2025, (1, 3, 5, 7, 9, 11)), (2026, (2, 4, 6, 8))):
        for m in months:
            for t in rnd.sample(topics, 2):
                k += 1
                add(f"Fair practices on recovery: {t} ({year}-{m:02d})", "circular", "Reserve Regulator (synthetic)", f"REG/FP/{year}/{k:03d}", date(year, m, 1), _regulator(t, rnd))
    topics_l = ["calling hours policy", "contact frequency policy", "consent management policy", "identity verification standard", "notice management policy", "agency code of conduct",
                "recording and retention policy", "escalation matrix", "outsourcing policy", "vulnerable borrower handling", "language policy", "settlement policy"]
    for code, L in LENDERS.items():
        for i, t in enumerate(topics_l):
            versions = 3 if t in ("calling hours policy", "contact frequency policy") and code == "BANK01" else 2 if t in ("calling hours policy", "contact frequency policy") else 1
            for v in range(1, versions + 1):
                eff = (L["hours"] if "hours" in t else L["cap"])[min(v - 1, len(L["hours" if "hours" in t else "cap"]) - 1)][0] if "hours" in t or "frequency" in t else date(2025, 1 + i % 9, 1)
                add(f"{L['name']}: {t} v{v}.0", "policy", L["name"], f"{code}/POL/{i + 1:02d}/v{v}", eff, _lender_policy(code, t, v, rnd))
        add(f"{L['name']}: delegation of authority grid", "policy", L["name"], f"{code}/DOA/01", date(2025, 1, 1), _delegation(code, rnd))
        for q in range(1, 13):  # the lender's own versions of the fair-practice rules, per topic and year
            t = topics[q % len(topics)]
            add(f"{L['name']}: implementation note on {t} ({q})", "policy", L["name"], f"{code}/IMP/{q:02d}", date(2025 + q // 8, 1 + q % 12, 1), _regulator(t, rnd))
    sop_topics = ["pre-call identity verification", "WhatsApp template usage", "recording retention", "notice dispatch", "agent certification renewal", "calling window configuration",
                  "attempt counting", "consent capture"]
    n = 0
    while len(docs) < 200:
        n += 1
        code = list(LENDERS)[n % 3]
        t = sop_topics[n % len(sop_topics)]
        add(f"SOP: {t} ({LENDERS[code]['name']}, edition {n})", "sop", LENDERS[code]["name"], f"{code}/SOP/{n:03d}", date(2025, 1 + n % 12, 1 + n % 27), _sop(t, rnd))
    return docs[:200]


def load_policy_library(conn, rnd: random.Random) -> int:
    """Replace the seeded policy documents in the knowledge base. Documents added by people are left alone."""
    ids = [r[0] for r in conn.execute("SELECT doc_id FROM audit.kb_document WHERE uploaded_by = %s", (SEED_USER,)).fetchall()]
    if ids:
        conn.execute("DELETE FROM audit.guardrail WHERE source_doc_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM audit.kb_clause WHERE doc_id = ANY(%s)", (ids,))
        conn.execute("DELETE FROM audit.kb_document WHERE doc_id = ANY(%s)", (ids,))
    docs = build_documents(rnd)
    for d in docs:
        doc_id = conn.execute("""INSERT INTO audit.kb_document (title, issuer, doc_type, reference_no, effective_date, body, uploaded_by)
                                 VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING doc_id""",
                              (d["title"], d["issuer"], d["doc_type"], d["reference_no"], d["effective_date"], d["body"], SEED_USER)).fetchone()[0]
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO audit.kb_clause (doc_id, seq, clause_no, body) VALUES (%s, %s, %s, %s)",
                            [(doc_id, i, no, body) for i, (no, body) in enumerate(split_clauses(d["body"]), 1)])
    return len(docs)
