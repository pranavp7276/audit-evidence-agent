"""Populate the CN Core replica (db/migrations/V005) with realistic, seeded collections data, and write the
ground-truth gap key for the audit checks.

Synthetic: no real borrowers. Shapes follow the CN_CORE / UAMDB tables; the compliance.* tables are our design
(docs/cn_core_model.md). Problems are seeded at random, and the gap key comes from an independent oracle that
applies the rules to the generated rows, not from the platform's checks.

Two dialers on purpose: SlashRTC logs call times in IST, CognifAI in UTC, with different session-id formats.
A few calls are mirrored in both dialers (authoritative xref), a session has several status rows, and the D12
rules change over time (calling-window end, daily attempt cap).

  python scripts/gen_cn_core.py [--seed 7]      reloads the tables in DATABASE_URL (truncates first)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = date(2026, 11, 19)
START, END = date(2026, 1, 5), date(2026, 10, 29)

N_CUSTOMERS, N_ACCOUNTS, SAMPLE = 1500, 1800, 300
STATES = ["MH", "KA", "TN", "DL", "GJ", "KL", "UP", "WB", "RJ", "TS"]
NATIONAL_HOLIDAYS = {
    date(2026, 1, 26): "Republic Day", date(2026, 3, 4): "Holi", date(2026, 4, 3): "Good Friday", date(2026, 8, 15): "Independence Day",
    date(2026, 10, 2): "Gandhi Jayanti", date(2026, 11, 8): "Diwali", date(2026, 12, 25): "Christmas",
    date(2027, 1, 26): "Republic Day", date(2027, 3, 22): "Holi", date(2027, 8, 15): "Independence Day",
}
STATE_HOLIDAYS = [(date(2026, 1, 15), "Pongal", "TN"), (date(2026, 5, 1), "Maharashtra Day", "MH"), (date(2026, 8, 26), "Onam", "KL"),
                  (date(2026, 11, 1), "Karnataka Rajyotsava", "KA")]

# D12 rules, effective-dated (end exclusive). Re-stated independently in the oracle below.
WINDOW_START = time(8, 0)
WINDOW_END = [(date(2026, 1, 1), date(2026, 4, 1), time(19, 0)), (date(2026, 4, 1), None, time(18, 50))]
DAILY_CAP = [(date(2026, 1, 1), date(2026, 6, 1), 4), (date(2026, 6, 1), None, 5)]
NOTICE_DISPATCH_BDAYS, NOTICE_SERVE_BDAYS = 3, 7
TOTAL_LOAN_DUES_CATEGORIES = ("COLLECTIONS", "SERVICE", "PROMOTIONAL")


def pick(rules, d):
    for a, b, v in rules:
        if a <= d and (b is None or d < b):
            return v
    raise ValueError(d)


def bdays(start: date, end: date, hol: set[date]) -> int:
    """Business days in (start, end]: Mon-Fri, not a national holiday."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in hol:
            n += 1
    return n


def add_bdays(start: date, n: int, hol: set[date]) -> date:
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in hol:
            n -= 1
    return d


def main(seed: int) -> None:
    load_dotenv(ROOT / ".env")
    rnd = random.Random(seed)
    nat = set(NATIONAL_HOLIDAYS)
    t = defaultdict(list)  # table -> rows (dicts), loaded in dependency order at the end

    # ------------------------------------------------------------ UAMDB
    org_types = [(1, "LENDER", "Lender", "INTERNAL"), (2, "TELE_AGENCY", "Tele-calling agency", "AGENCY"), (3, "FIELD_AGENCY", "Field agency", "AGENCY")]
    for i, c, n, cat in org_types:
        t["uamdb.organization_type"].append(dict(organization_type_id=i, organization_type_code=c, organization_type_name=n,
                                                  organization_type_category=cat, authentication_type="SSO" if i == 1 else "PASSWORD",
                                                  two_factor_auth="Y" if i == 1 else "N", organization_type_desc=n))
    orgs = [(1, "CNFIN", "CN Finance Ltd", 1, "SlashRTC"), (2, "APEX", "Apex Tele Services", 2, "SLASHRTC"), (3, "NSTAR", "Northstar BPO", 2, "SLASHRTC"),
            (4, "MERID", "Meridian Voice", 2, "COGNIFAI"), (5, "SUNRS", "Sunrise Contact Centre", 2, "BOTH"),
            (6, "FLD01", "Pioneer Field Recovery", 3, None), (7, "FLD02", "Delta Field Services", 3, None)]
    for oid, code, name, ot, _ in orgs:
        t["uamdb.organization"].append(dict(organization_id=oid, organization_code=code, organization_name=name, organization_type_id=ot,
                                            registered_address=f"{rnd.randint(1, 99)} Business Park", registered_contact_no=f"022{rnd.randint(10000000, 99999999)}",
                                            organization_email=f"ops@{code.lower()}.example", city=rnd.choice(["Mumbai", "Pune", "Chennai", "Bengaluru"]),
                                            state=rnd.choice(STATES), postal_code=str(rnd.randint(400000, 600000)), country="IN",
                                            contact_person_name="Ops Manager", contact_person_designation="Manager",
                                            contact_person_contact_no=f"98{rnd.randint(10000000, 99999999)}", organization_status="ACTIVE"))
    roles = [(1, "Collections Admin", 1, "ADMIN"), (2, "Tele Agent", 2, "TELE"), (3, "Tele Supervisor", 2, "TELE"), (4, "Compliance Officer", 1, "COMPLIANCE"), (5, "Field Agent", 3, "FIELD")]
    for rid, name, oid, rt in roles:
        t["uamdb.roles"].append(dict(role_id=rid, role_name=name, role_description=name, organization_id=oid, role_type=rt, parent_role_id=None,
                                     admin_role_flag="Y" if rid == 1 else "N", super_admin_role_flag="N"))
    first = ["Aarav", "Vivaan", "Aditya", "Diya", "Ananya", "Isha", "Rohan", "Kavya", "Arjun", "Meera", "Karthik", "Neha", "Sandeep", "Pooja", "Imran", "Farah", "Suresh", "Lakshmi", "Manoj", "Sunita"]
    last = ["Sharma", "Iyer", "Reddy", "Patel", "Khan", "Nair", "Gupta", "Singh", "Das", "Joshi", "Menon", "Verma", "Rao", "Chopra", "Pillai"]
    users, agents_by_org, emp_seq = [], defaultdict(list), 10000
    uid = 0

    def add_user(org, role, desig, with_code=True, dept="Collections"):
        nonlocal uid, emp_seq
        uid += 1
        emp_seq += 1
        fn, ln = rnd.choice(first), rnd.choice(last)
        u = dict(user_id=uid, user_name=f"{fn.lower()}.{ln.lower()}{uid}", organization_id=org, first_name=fn, middle_name=None, last_name=ln, role_id=role,
                 designation=desig, department=dept, employee_code=f"EMP{emp_seq}" if with_code else None, reporting_manager_id=None,
                 base_branch_code=f"BR{rnd.randint(1, 20):02d}", contact_no=f"9{rnd.randint(100000000, 999999999)}", email=f"user{uid}@example.test",
                 city=rnd.choice(["Mumbai", "Pune", "Chennai", "Bengaluru"]), state=rnd.choice(STATES), postal_code=str(rnd.randint(400000, 600000)),
                 country="IN", gender=rnd.choice(["M", "F"]), preferred_language=rnd.choice(["en", "hi", "ta", "mr"]), user_status="ACTIVE")
        users.append(u)
        t["uamdb.users"].append(u)
        t["uamdb.user_role_link"].append(dict(user_role_link_id=uid, user_id=uid, role_id=role))
        return u

    for _ in range(5):
        add_user(1, 4, "Compliance Officer", dept="Compliance")
    for _ in range(3):
        add_user(1, 1, "Collections Admin", dept="Operations")
    supervisors = {}
    for oid in (2, 3, 4, 5):
        supervisors[oid] = [add_user(oid, 3, "Tele Supervisor") for _ in range(2)]
        for _ in range(30):
            a = add_user(oid, 2, "Tele Agent", with_code=rnd.random() > 0.02)  # a few agents have no employee code on file
            a["reporting_manager_id"] = supervisors[oid][0]["user_id"]
            agents_by_org[oid].append(a)
    all_agents = [a for v in agents_by_org.values() for a in v]

    # ------------------------------------------------------------ dialers, campaigns, process types and instances
    t["compliance.dialer_config"] += [dict(dialer_code="SLASHRTC", dialer_name="SlashRTC", timezone="Asia/Kolkata", session_id_format="SRTC-YYYYMMDD-NNNNNN"),
                                      dict(dialer_code="COGNIFAI", dialer_name="CognifAI", timezone="UTC", session_id_format="cgn-<uuid>")]
    dialer_tz = {"SLASHRTC": IST, "COGNIFAI": UTC}
    agency_dialers = {2: {"MANUAL": "SLASHRTC", "CAMPAIGN": "SLASHRTC"}, 3: {"MANUAL": "SLASHRTC", "CAMPAIGN": "SLASHRTC"},
                      4: {"MANUAL": "COGNIFAI", "CAMPAIGN": "COGNIFAI"}, 5: {"MANUAL": "SLASHRTC", "CAMPAIGN": "COGNIFAI"}}
    ptype, pinst = {}, {}
    t["cn_core.tele_campaign"] += [dict(id=oid, tele_campaign_name=f"{orgs[oid - 1][2]} collections", campaign_owner_id=supervisors[oid][0]["user_id"],
                                        campaign_status="A", created_date=datetime(2025, 12, 1)) for oid in (2, 3, 4, 5)]
    tid = iid = 0
    for oid in (2, 3, 4, 5):
        for mode in ("MANUAL", "CAMPAIGN"):
            tid += 1
            d = agency_dialers[oid][mode]
            ptype[(oid, mode)] = tid
            t["cn_core.tele_process_type"].append(dict(id=tid, process_type_name=f"{orgs[oid - 1][2]} {mode.title()}", process_type_mode=mode, campaign_id=oid,
                                                       process_type_status="ACTIVE", calling_ratio=1 if mode == "MANUAL" else 3, dialer_process_id=9000 + tid,
                                                       wait_time=30, times_to_try=3, sticky_agent_flag=0, inbound_delay_time=10, process_call_attempts=3,
                                                       process_max_calls_per_day=5, created_date=date(2025, 12, 1), dialer_code=d))
            for m in range(1, 11):  # one run per month
                iid += 1
                pinst[(oid, mode, m)] = iid
                t["cn_core.tele_process_instance"].append(dict(id=iid, process_type_id=tid, process_name=f"{orgs[oid - 1][2]} {mode.title()} 2026-{m:02d}",
                                                               process_mode=mode, campaign_id=oid, process_status="COMPLETED", calling_ratio=1 if mode == "MANUAL" else 3,
                                                               dialer_process_id=9000 + tid, process_start_date=date(2026, m, 1), process_start_time=datetime(2026, m, 1, 8, 0),
                                                               process_end_date=date(2026, m, 28), process_end_time=datetime(2026, m, 28, 19, 0), number_of_accounts=0,
                                                               number_of_agents=30, supervisor_id=supervisors[oid][0]["user_id"], dialer_code=d))
    link = 0
    for oid, ags in agents_by_org.items():
        for a in ags:
            link += 1
            t["cn_core.tele_process_instance_user_link"].append(dict(id=link, tele_process_instance_id=pinst[(oid, "MANUAL", 1)], user_id=a["user_id"], user_group_id=oid))

    # ------------------------------------------------------------ D12 rules, holidays, notice policy
    rid = 0

    def rule(key, val, unit, frm, to, **kw):
        nonlocal rid
        rid += 1
        t["compliance.calling_policy_rule"].append(dict(rule_id=rid, policy_code="D12", rule_key=key, rule_value=val, unit=unit, effective_from=frm, effective_to=to,
                                                        counting_unit=kw.get("cu"), counting_rule=kw.get("cr"), note=kw.get("note")))
    rule("calling_window_start", "08:00", "local_time", date(2026, 1, 1), None, note="Borrower local time (IST); inclusive")
    for a, b, v in WINDOW_END:
        rule("calling_window_end", f"{v:%H:%M}", "local_time", a, b, note="Borrower local time (IST); exclusive")
    for a, b, v in DAILY_CAP:
        rule("max_attempts_per_contact_per_day", str(v), "attempts", a, b, cu="CONTACT_NUMBER",
             cr="Distinct outbound call sessions to the same contact number on one IST calendar day; excludes SYSTEM_FAILURE; a session mirrored across dialers counts once")
    rule("notice_dispatch_sla_business_days", str(NOTICE_DISPATCH_BDAYS), "business_days", date(2026, 1, 1), None, note="Trigger date to dispatch; Mon-Fri excluding national holidays; day N inclusive")
    rule("notice_service_sla_business_days", str(NOTICE_SERVE_BDAYS), "business_days", date(2026, 1, 1), None, note="Trigger date to service; same calendar; day N inclusive")
    hid = 0
    for d, n in sorted(NATIONAL_HOLIDAYS.items()):
        hid += 1
        t["compliance.holiday_calendar"].append(dict(holiday_id=hid, holiday_date=d, holiday_name=n, scope="national", state=None))
    for d, n, s in STATE_HOLIDAYS:
        hid += 1
        t["compliance.holiday_calendar"].append(dict(holiday_id=hid, holiday_date=d, holiday_name=n, scope="state", state=s))

    # ------------------------------------------------------------ customers, accounts, cases
    names_f = ["Ravi", "Anil", "Sunil", "Priya", "Deepa", "Rekha", "Vikram", "Ajay", "Sneha", "Rahul", "Nisha", "Gopal", "Jyoti", "Harish", "Usha"]
    custs, ccn, cc_id = [], defaultdict(list), 0
    used_nums = set()

    def mobile():
        while True:
            n = f"{rnd.choice('6789')}{rnd.randint(100000000, 999999999)}"
            if n not in used_nums:
                used_nums.add(n)
                return n
    for i in range(1, N_CUSTOMERS + 1):
        cid = 5_000_000 + i
        fn, ln = rnd.choice(names_f), rnd.choice(last)
        c = dict(id=cid, institution_code="CNFIN" if rnd.random() < 0.85 else "CNHF", source_system_code="LMS", customer_number=f"C{rnd.randint(10**8, 10**9 - 1)}",
                 unified_customer_id=f"U{cid}", customer_name=f"{fn} {ln}", customer_first_name=fn, customer_last_name=ln, father_name=f"{rnd.choice(names_f)} {ln}",
                 customer_status_id=1, gender_code=rnd.choice(["M", "F"]), customer_category_code="I", customer_type_code="INDIVIDUAL",
                 branch_code=f"BR{rnd.randint(1, 20):02d}", occupation=rnd.choice(["Salaried", "Self-employed", "Trader", "Farmer"]),
                 preferred_language_code=rnd.choice(["en", "hi", "ta", "mr"]), open_date=date(2023, 1, 1) + timedelta(days=rnd.randint(0, 900)),
                 birth_date=date(1960, 1, 1) + timedelta(days=rnd.randint(0, 14000)))
        c["state"] = rnd.choice(STATES)
        custs.append(c)
        for seq, typ in enumerate(["PRIMARY"] + (["ALTERNATE"] if rnd.random() < 0.4 else []), 1):
            cc_id += 1
            row = dict(id=cc_id, customer_id=cid, category="MOBILE", sequence_no=seq, contact_type=typ, contact_no=mobile(), contact_number_type="MOBILE", std_code=None,
                       isd_code="91", contact_name=c["customer_name"], verified_status=rnd.choice(["VERIFIED", "UNVERIFIED"]))
            t["cn_core.customer_contact_number"].append(row)
            ccn[cid].append(row)
    accts, accts_by_cust = [], defaultdict(list)
    seqn = 0
    for i in range(1, N_ACCOUNTS + 1):
        cust = custs[i - 1] if i <= N_CUSTOMERS else rnd.choice(custs)  # every customer has a loan; some have a second
        aid = 7_000_000 + i
        seqn += 1
        prefix = "CNF" if cust["institution_code"] == "CNFIN" else "CNH"
        loan = rnd.choice([50000, 100000, 250000, 500000, 1000000])
        dpd = rnd.choice([5, 15, 35, 62, 95, 140, 200])
        a = dict(id=aid, institution_code=cust["institution_code"], source_system_code="LMS", account_number=f"{prefix}{rnd.randint(10**8, 10**9 - 1)}",
                 account_type_code="LN", customer_id=cust["id"], branch_code=cust["branch_code"], product_category_code="RETAIL",
                 product_segment_code=rnd.choice(["PL", "BL", "TW"]), product_group_code="UNSECURED", product_code=rnd.choice(["PL01", "BL02", "TW03"]), account_status_id=1,
                 loan_amount=loan, sanctioned_amount=loan, disbursed_amount=loan, open_date=date(2024, 1, 1) + timedelta(days=rnd.randint(0, 600)),
                 disbursal_date=date(2024, 1, 5) + timedelta(days=rnd.randint(0, 600)), maturity_date=date(2027, 1, 1) + timedelta(days=rnd.randint(0, 900)), close_date=None,
                 tenure=rnd.choice([12, 24, 36, 48]), interest_rate=round(rnd.uniform(11, 24), 5), installment_amount=round(loan / 24, 3), repayment_cycle_day=rnd.randint(1, 28),
                 due_date=date(2026, 10, rnd.randint(1, 28)), next_due_date=date(2026, 11, rnd.randint(1, 28)), principal_outstanding_amount=round(loan * rnd.uniform(.3, .9), 3),
                 interest_outstanding_amount=round(loan * .03, 3), total_outstanding_amount=round(loan * rnd.uniform(.4, 1.0), 3), total_overdue_amount=round(loan / 24 * dpd / 30, 3),
                 dpd=dpd, delinquency_bucket_code=("0-30" if dpd <= 30 else "31-60" if dpd <= 60 else "61-90" if dpd <= 90 else "90+"),
                 last_payment_received_date=datetime(2026, 1, 1) + timedelta(days=rnd.randint(0, 200)), last_payment_received_amount=round(loan / 24, 3),
                 npa_flag="Y" if dpd > 90 else "N", overdue_since_date=date(2026, 10, 1) - timedelta(days=dpd))
        a["_cust"] = cust
        accts.append(a)
        accts_by_cust[cust["id"]].append(a)
    # ambiguous loan references: a few account numbers exist under both institutions
    cnf = [a for a in accts if a["institution_code"] == "CNFIN"]
    cnh = [a for a in accts if a["institution_code"] == "CNHF"]
    ambiguous = []
    for x, y in zip(rnd.sample(cnf, 12), rnd.sample(cnh, 12)):
        y["account_number"] = x["account_number"]
        ambiguous.append((x, y))
    acc_cc = 0
    for a in accts:
        for r in ccn[a["customer_id"]]:
            acc_cc += 1
            t["cn_core.account_customer_contact_number"].append(dict(id=acc_cc, account_id=a["id"], customer_id=a["customer_id"], category=r["category"], sequence_no=r["sequence_no"],
                                                                     contact_type=r["contact_type"], contact_no=r["contact_no"], contact_number_type="MOBILE", std_code=None,
                                                                     isd_code="91", contact_name=r["contact_name"]))
    case_agent = {}
    for i, a in enumerate(accts, 1):
        oid = rnd.choice([2, 3, 4, 5])
        ag = rnd.choice(agents_by_org[oid])
        case_agent[a["id"]] = (oid, ag)
        t["cn_core.collection_case"].append(dict(id=8_000_000 + i, case_year=2026, case_month=1, case_start_date=datetime(2026, 1, 1), case_end_date=None, case_status_id=1,
                                                 collection_status="ACTIVE", resolution_status="OPEN", account_id=a["id"], case_owner_user_id=supervisors[oid][0]["user_id"],
                                                 allocated_collection_user_id=None, allocated_collection_agency_id=None, allocated_tele_call_user_id=ag["user_id"],
                                                 allocated_tele_call_agency_id=oid, allocated_tele_call_agency_user_id=supervisors[oid][0]["user_id"], case_start_dpd=a["dpd"],
                                                 dpd=a["dpd"], delinquency_bucket_code=a["delinquency_bucket_code"], total_outstanding_amount=a["total_outstanding_amount"]))
    t["cn_core.disposition_group"] += [dict(disposition_group_code=g, disposition_group_name=n) for g, n in
                                       [("CONTACT", "Contacted"), ("NOCONTACT", "Not contacted"), ("PROMISE", "Promise to pay")]]
    t["cn_core.disposition_code"] += [dict(disposition_code=c, disposition_code_name=n, disposition_group_code=g, disposition_level="1", sub_disposition_label_name=n) for c, n, g in
                                      [("PTP", "Promise to pay", "PROMISE"), ("RTP", "Refused to pay", "CONTACT"), ("CALLBACK", "Call back", "CONTACT"), ("WRONGNO", "Wrong number", "NOCONTACT"),
                                       ("NOANS", "No answer", "NOCONTACT")]]

    # ------------------------------------------------------------ calls
    sessions = []  # canonical sessions (dicts) plus mirror rows, used for loading and the oracle
    tpicl = teia = act = rec = seg = xr = 0
    day_span = (END - START).days

    def local_dt(d: date, h: int, m: int, s: int = 0) -> datetime:
        return datetime.combine(d, time(h, m, s), tzinfo=IST)

    def new_session_id(dialer: str, ts: datetime, n: int) -> str:
        return f"SRTC-{ts:%Y%m%d}-{n:06d}" if dialer == "SLASHRTC" else "cgn-" + str(uuid.UUID(int=rnd.getrandbits(128)))[:23]

    sess_n = [0]

    def make_session(a: dict, contact: str, start_ist: datetime, forced_status: str | None = None, direction: str = "OUTBOUND") -> dict:
        oid, ag = case_agent[a["id"]]
        if rnd.random() < 0.1:  # cross-agency call
            oid = rnd.choice([2, 3, 4, 5])
            ag = rnd.choice(agents_by_org[oid])
        mode = rnd.choices(["MANUAL", "CAMPAIGN"], [0.45, 0.55])[0]
        dialer = agency_dialers[oid][mode]
        sess_n[0] += 1
        status = forced_status or rnd.choices(["CONNECTED", "NO_ANSWER", "BUSY", "SYSTEM_FAILURE"], [0.5, 0.33, 0.12, 0.05])[0]
        connected = status == "CONNECTED"
        dur = rnd.randint(40, 900) if connected else 0
        return dict(account=a, contact=contact, start=start_ist, status=status, connected=connected, duration=dur, direction=direction, org=oid, agent=ag, mode=mode, dialer=dialer,
                    sid=new_session_id(dialer, start_ist, sess_n[0]), mirror=None)

    cust_contacts = {cid: [r["contact_no"] for r in rows] for cid, rows in ccn.items()}
    for a in accts:
        cid = a["customer_id"]
        nums = cust_contacts[cid]
        days = sorted(rnd.sample(range(day_span), rnd.randint(5, 9)))
        for d in days:
            day = START + timedelta(days=d)
            contact = nums[0] if rnd.random() < 0.8 else nums[-1]
            start = local_dt(day, 9, 0) + timedelta(seconds=rnd.randint(0, 8 * 3600 + 1800))  # 09:00-17:30
            sessions.append(make_session(a, contact, start))
        if rnd.random() < 0.03:  # an inbound call: excluded from every outbound check
            day = START + timedelta(days=rnd.randrange(day_span))
            sessions.append(make_session(a, nums[0], local_dt(day, 11, 0), "CONNECTED", "INBOUND"))

    by_acct = defaultdict(list)
    for s in sessions:
        by_acct[s["account"]["id"]].append(s)
    # outside-window calls: the effective rule decides (18:51-18:59 is a gap only from 1 April)
    for a in accts:
        ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
        if ss and rnd.random() < 0.06:
            s = rnd.choice(ss)
            kind = rnd.random()
            day = s["start"].date()
            if kind < 0.35:
                s["start"] = local_dt(day, 18, rnd.randint(51, 59), rnd.randint(0, 59))
            elif kind < 0.7:
                s["start"] = local_dt(day, rnd.choice([19, 20]), rnd.randint(0, 40))
            else:
                s["start"] = local_dt(day, rnd.choice([6, 7]), rnd.randint(0, 59))
    # frequency: bursts on one contact number in one day (cap+1 breaches, exactly cap is fine, mirrored duplicates do not add up)
    for a in accts:
        ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
        if not ss:
            continue
        r = rnd.random()
        if r < 0.10:
            base = rnd.choice(ss)
            day = base["start"].date()
            cap = pick(DAILY_CAP, day)
            have = sum(1 for s in ss if s["contact"] == base["contact"] and s["start"].date() == day)
            extra = (cap + 1 if r < 0.05 else cap) - have  # first half breach, second half exactly at the cap
            for k in range(max(extra, 0)):
                s2 = make_session(a, base["contact"], local_dt(day, 9 + (k % 8), rnd.randint(0, 59)), "NO_ANSWER")
                sessions.append(s2)
                by_acct[a["id"]].append(s2)
    # mirrored duplicates: same call also logged by the other dialer (authoritative xref says count once)
    mirrors = []
    for s in sessions:
        if s["direction"] == "OUTBOUND" and rnd.random() < 0.02:
            other = "COGNIFAI" if s["dialer"] == "SLASHRTC" else "SLASHRTC"
            sess_n[0] += 1
            m = dict(s, dialer=other, sid=new_session_id(other, s["start"], sess_n[0]), mirror=s, status=s["status"])
            mirrors.append(m)
    # force a burst day where the mirrors would push a naive count over the cap
    for a in rnd.sample(accts, 8):
        ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
        if not ss:
            continue
        base = ss[0]
        day = base["start"].date()
        cap = pick(DAILY_CAP, day)
        have = [s for s in ss if s["contact"] == base["contact"] and s["start"].date() == day]
        for k in range(cap - len(have)):
            s2 = make_session(a, base["contact"], local_dt(day, 10 + k % 6, rnd.randint(0, 59)), "NO_ANSWER")
            sessions.append(s2)
            by_acct[a["id"]].append(s2)
            have.append(s2)
        for s2 in have[:2]:
            other = "COGNIFAI" if s2["dialer"] == "SLASHRTC" else "SLASHRTC"
            sess_n[0] += 1
            mirrors.append(dict(s2, dialer=other, sid=new_session_id(other, s2["start"], sess_n[0]), mirror=s2))

    sessions.sort(key=lambda s: (s["start"], s["sid"]))

    def dialer_ts(ts_ist: datetime, dialer: str) -> datetime:
        return ts_ist.astimezone(dialer_tz[dialer]).replace(tzinfo=None)

    emp_valid = {}
    # certifications (keyed by employee code)
    cert_id = 0
    for u in all_agents:
        code = u["employee_code"]
        if not code:
            continue
        r = rnd.random()
        spans = []
        if r < 0.08:
            spans = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 120)), date(2026, 3, 1) + timedelta(days=rnd.randint(0, 180)))]
        elif r < 0.12:
            lapse = date(2026, 3, 1) + timedelta(days=rnd.randint(0, 120))
            spans = [(date(2025, 1, 1), lapse), (lapse + timedelta(days=rnd.randint(30, 70)), date(2027, 12, 31))]
        elif r < 0.15:
            spans = []  # never certified
        else:
            spans = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 200)), date(2027, 6, 30))]
        emp_valid[code] = spans
        for vf, vt in spans:
            cert_id += 1
            t["compliance.collector_certification"].append(dict(cert_id=cert_id, employee_code=code, certification="RECOVERY_AGENT_CERT", certificate_no=f"RAC-{cert_id:06d}",
                                                                valid_from=vf, valid_to=vt, issuer="Indian Institute of Collections"))

    # ------------------------------------------------------------ write call logs, activities, recordings and transcripts
    all_rows = [(s, None) for s in sessions] + [(m, m["mirror"]) for m in mirrors]
    all_rows.sort(key=lambda p: (p[0]["start"], p[0]["sid"]))
    recorded: dict[tuple[str, str], str] = {}
    for s, mirror_of in all_rows:
        a, dialer, sid = s["account"], s["dialer"], s["sid"]
        oid, ag = s["org"], s["agent"]
        inst = pinst[(oid, s["mode"], s["start"].month)] if s["mode"] else None
        end_ist = s["start"] + timedelta(seconds=s["duration"])
        rows = []
        if s["connected"]:
            rows = [("CONNECTED", s["start"], end_ist), ("DISPOSED", s["start"], end_ist)]
        elif s["status"] == "NO_ANSWER" and rnd.random() < 0.5:
            rows = [("INITIATED", s["start"], s["start"]), ("NO_ANSWER", s["start"], s["start"] + timedelta(seconds=30))]
        else:
            rows = [(s["status"], s["start"], s["start"] + timedelta(seconds=rnd.randint(5, 30)))]
        first_log = None
        for st, a0, a1 in rows:
            tpicl += 1
            first_log = first_log or tpicl
            t["cn_core.tele_process_instance_call_logs"].append(dict(
                id=tpicl, tele_process_instance_id=inst, call_contact_number=s["contact"], user_contact_number=ag["contact_no"], call_direction=s["direction"], call_status=st,
                call_session_id=sid, call_start_date_time=dialer_ts(a0, dialer), call_end_date_time=dialer_ts(a1, dialer), call_duration=s["duration"] if st in ("CONNECTED", "DISPOSED") else 0,
                call_recording_link=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3" if s["connected"] else None, call_user_id=ag["user_id"], dialer_code=dialer))
        act_id = None
        if s["connected"] and mirror_of is None:
            act += 1
            act_id = act
            disp = rnd.choice(["PTP", "RTP", "CALLBACK"])
            t["cn_core.activity_log"].append(dict(
                id=act, customer_id=a["customer_id"], account_id=a["id"], activity_level="A", activity_type_code="CALL", activity_sub_type_code="TELE", activity_code="OUTBOUND_CALL",
                target_party_type_code="BORROWER", target_party_customer_id=a["customer_id"], target_party_contact_number_category="MOBILE", target_party_contact_number_id=None,
                target_party_other_contact_number=s["contact"], activity_datetime=end_ist.replace(tzinfo=None), target_party_contacted_status="Y",
                contacted_party_name=a["_cust"]["customer_name"], contacted_party_relation="SELF", contacted_party_contact_number=s["contact"],
                disposition_group_code="PROMISE" if disp == "PTP" else "CONTACT", disposition_code=disp, disposition_sub_code=None, next_activity_code="CALL",
                next_activity_datetime=end_ist.replace(tzinfo=None) + timedelta(days=3), ptp_amount=round(a["installment_amount"], 3) if disp == "PTP" else None,
                ptp_payment_mode="UPI" if disp == "PTP" else None, user_remarks=None, party_interaction_status="CONNECTED", activity_detail=None,
                created_date=end_ist.replace(tzinfo=None), created_by=ag["user_id"], creation_mode="DIALER", activity_done_by=ag["user_id"], source_system_code=dialer,
                external_disposition_code=None, call_start_datetime=s["start"].replace(tzinfo=None), call_end_datetime=end_ist.replace(tzinfo=None),
                call_recording_url=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3", call_status="CONNECTED"))
        teia += 1
        t["cn_core.tele_process_instance_activity"].append(dict(id=teia, tele_process_instance_id=inst, account_id=a["id"], customer_id=a["customer_id"], call_session_id=sid,
                                                                call_log_id=first_log, activity_status="DONE" if act_id else "NONE", activity_log_id=act_id, dialer_code=dialer))
        if mirror_of is not None:
            xr += 1
            t["compliance.call_session_xref"].append(dict(xref_id=xr, dialer_code=mirror_of["dialer"], call_session_id=mirror_of["sid"], mirror_dialer_code=dialer, mirror_session_id=sid,
                                                          relation="MIRROR", canonical_dialer_code=mirror_of["dialer"]))
        if s["connected"] and mirror_of is None:
            # recording retrieval status and transcript
            rr = rnd.random()
            storage = "AVAILABLE" if rr < 0.94 else "NOT_FOUND" if rr < 0.97 else "RETRIEVAL_FAILED"
            rec += 1
            t["compliance.call_recording"].append(dict(recording_id=rec, dialer_code=dialer, call_session_id=sid, recording_url=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3" if storage != "NOT_FOUND" else None,
                                                       duration_sec=s["duration"] if storage == "AVAILABLE" else None, storage_status=storage, checked_at=datetime(2026, 11, 18, 6, 0),
                                                       note={"NOT_FOUND": "No object in the recording store for this session", "RETRIEVAL_FAILED": "Recording store returned an error",
                                                             "AVAILABLE": None}[storage]))
            scenario, transcript = "no_transcript", []
            if storage == "AVAILABLE" and s["direction"] == "OUTBOUND":
                x = rnd.random()
                disclose = rnd.random() < 0.8
                if x < 0.02:
                    scenario = "no_transcript"
                else:
                    if not disclose:
                        scenario = "no_disclosure"
                        transcript = [(2.0, "AGENT", "Hello, this is a collections call.", "NONE"), (20.0, "BORROWER", "Please call later.", "NONE")]
                    elif x < 0.06:
                        scenario = "disclosure_first"
                        transcript = [(3.0, "AGENT", "Your overdue amount is Rs 12,400.", "DUES_DISCLOSURE"), (30.0, "AGENT", "Please confirm your date of birth.", "IDENTITY_CHECK_REQUEST"),
                                      (45.0, "BORROWER", "It is 14 March 1988.", "IDENTITY_CHECK_PASS")]
                    elif x < 0.09:
                        scenario = "no_verification"
                        transcript = [(2.0, "AGENT", "Hello, calling about your loan.", "NONE"), (25.0, "AGENT", "You owe Rs 9,800 overdue.", "DUES_DISCLOSURE")]
                    elif x < 0.11:
                        scenario = "failed_then_disclosed"
                        transcript = [(10.0, "AGENT", "Please confirm your date of birth.", "IDENTITY_CHECK_REQUEST"), (20.0, "BORROWER", "I will not say.", "IDENTITY_CHECK_FAIL"),
                                      (40.0, "AGENT", "Your overdue amount is Rs 7,500.", "DUES_DISCLOSURE")]
                    elif x < 0.13:
                        scenario = "unclear"
                        transcript = [(10.0, "AGENT", "[inaudible] confirm [inaudible]", "UNCLEAR"), (35.0, "AGENT", "Your overdue amount is Rs 5,100.", "DUES_DISCLOSURE")]
                    else:
                        scenario = "ok"
                        v = round(rnd.uniform(10, 40), 1)
                        transcript = [(2.0, "AGENT", "Hello, collections call.", "NONE"), (v, "AGENT", "Please confirm your date of birth.", "IDENTITY_CHECK_REQUEST"),
                                      (round(v + 12, 1), "BORROWER", "It is 03 June 1990.", "IDENTITY_CHECK_PASS"), (round(v + 40, 1), "AGENT", "Your overdue amount is Rs 8,200.", "DUES_DISCLOSURE")]
                for i, (off, who, txt, tag) in enumerate(transcript, 1):
                    seg += 1
                    t["compliance.call_transcript_segment"].append(dict(segment_id=seg, dialer_code=dialer, call_session_id=sid, seq=i, start_offset_sec=off, speaker=who, utterance=txt, tag=tag))
            recorded[(dialer, sid)] = storage
            s["_storage"], s["_scenario"] = storage, scenario

    # ------------------------------------------------------------ messages, templates and consent
    t["cn_core.digital_template"] += [
        dict(template_id=1, sms_category="COLLECTIONS", sms_dlt_id="DLT1001", digital_channel="WHATSAPP", template_subject="EMI overdue reminder", template_body="Your EMI of Rs {amt} is overdue."),
        dict(template_id=2, sms_category="COLLECTIONS", sms_dlt_id="DLT1002", digital_channel="SMS", template_subject="EMI overdue reminder", template_body="EMI overdue. Pay via {link}."),
        dict(template_id=3, sms_category="SERVICE", sms_dlt_id="DLT2001", digital_channel="WHATSAPP", template_subject="Payment received", template_body="We received Rs {amt}. Thank you."),
        dict(template_id=4, sms_category="PROMOTIONAL", sms_dlt_id="DLT3001", digital_channel="SMS", template_subject="Pre-approved offer", template_body="Pre-approved top-up offer for you."),
        dict(template_id=5, sms_category="PROMOTIONAL", sms_dlt_id="DLT3002", digital_channel="WHATSAPP", template_subject="Festive offer", template_body="Festive offer on your next loan.")]
    msgs, consent_id, mid = [], 0, 0
    for a in accts:
        cid = a["customer_id"]
        nums = cust_contacts[cid]
        for _ in range(rnd.randint(2, 4)):
            day = START + timedelta(days=rnd.randrange(day_span))
            ts = local_dt(day, 9, 0) + timedelta(seconds=rnd.randint(0, 9 * 3600))
            ch = rnd.choices(["WHATSAPP", "SMS"], [0.7, 0.3])[0]
            r = rnd.random()
            tmpl = (1 if ch == "WHATSAPP" else 2) if r < 0.85 else 3 if r < 0.93 else (5 if ch == "WHATSAPP" else 4)
            if tmpl == 3 and ch == "SMS":
                tmpl = 2
            recip = nums[0] if rnd.random() < 0.85 else nums[-1]
            status = rnd.choices(["DELIVERED", "SENT", "READ", "FAILED"], [0.6, 0.2, 0.1, 0.1])[0]
            mid += 1
            m = dict(id=mid, a=a, ts=ts, ch=ch, tmpl=tmpl, cat={1: "COLLECTIONS", 2: "COLLECTIONS", 3: "SERVICE", 4: "PROMOTIONAL", 5: "PROMOTIONAL"}[tmpl], recip=recip, status=status)
            msgs.append(m)
    msgs.sort(key=lambda m: m["ts"])
    first_msg = {}
    for m in msgs:
        first_msg.setdefault((m["recip"], m["ch"]), m)
    consent_rows = []

    def add_consent(cid, no, ch, purpose, status, eff_utc):
        nonlocal consent_id
        consent_id += 1
        consent_rows.append(dict(consent_id=consent_id, customer_id=cid, contact_no=no, channel=ch, purpose=purpose, status=status, effective_at=eff_utc.replace(tzinfo=None),
                                 capture_source=rnd.choice(["app", "ivr", "branch", "web"])))
    cust_of_no = {r["contact_no"]: r["customer_id"] for rows in ccn.values() for r in rows}
    for (no, ch), m in first_msg.items():
        cid = cust_of_no[no]
        first_utc = m["ts"].astimezone(UTC)
        r = rnd.random()
        if r < 0.03:
            continue  # no consent on file at all
        if r < 0.09:  # captured after the first message, often hours later (time-zone trap)
            add_consent(cid, no, ch, "COLLECTIONS", "GRANTED", first_utc + (timedelta(hours=rnd.uniform(1, 5)) if rnd.random() < 0.5 else timedelta(days=rnd.uniform(0.5, 6))))
        else:
            add_consent(cid, no, ch, "COLLECTIONS", "GRANTED", first_utc - timedelta(days=rnd.uniform(2, 60)))
            if r < 0.13:  # revoked part-way: messages after the revocation are breaches
                add_consent(cid, no, ch, "COLLECTIONS", "REVOKED", first_utc + timedelta(days=rnd.uniform(20, 120)))
        if rnd.random() < 0.3:  # separate promotional consent for some
            add_consent(cid, no, ch, "PROMOTIONAL", "GRANTED", first_utc - timedelta(days=rnd.uniform(2, 60)))
    for m in msgs:
        a = m["a"]
        t["cn_core.communication_dashboard_t"].append(dict(
            id=m["id"], account_id=a["id"], account_number=a["account_number"], message_datetime=m["ts"].replace(tzinfo=None), channel=m["ch"], rule_name=f"RULE_{m['cat']}",
            message_status="SENT" if m["status"] != "FAILED" else "FAILED", customer_id=a["customer_id"], customer_name=a["_cust"]["customer_name"], message_type=m["cat"], language="en",
            sms_contact_no=m["recip"], sms_final_message=f"Template {m['tmpl']}", status=m["status"], delivery_status=m["status"],
            delivery_datetime=(m["ts"] + timedelta(seconds=20)).replace(tzinfo=None) if m["status"] != "FAILED" else None, template_id=m["tmpl"]))
    t["compliance.customer_consent"] += consent_rows

    # ------------------------------------------------------------ notices
    notice_rows, nid, ndoc = [], 0, 0
    for a in accts:
        if rnd.random() >= 0.65:
            continue
        stt = a["_cust"]["state"]
        for _ in range(200):
            trig = date(2026, 1, 2) + timedelta(days=rnd.randint(0, 300))
            if trig.weekday() >= 5 or trig in nat:
                continue
            both = nat | {d for d, _, s in STATE_HOLIDAYS if s == stt}
            r = rnd.random()
            dd = rnd.randint(1, NOTICE_DISPATCH_BDAYS) if r > 0.12 else rnd.randint(NOTICE_DISPATCH_BDAYS + 1, 8)
            disp = add_bdays(trig, dd, nat)
            r2 = rnd.random()
            sd = rnd.randint(dd, max(dd, NOTICE_SERVE_BDAYS)) if r2 > 0.10 else rnd.randint(max(dd, NOTICE_SERVE_BDAYS) + 1, 12)
            served = add_bdays(trig, max(sd, dd), nat)
            if r < 0.03:
                disp = served = None  # never dispatched
            elif r2 < 0.04:
                served = None  # dispatched but never served
            # keep state-holiday ambiguity out of the data
            def late(x, lim, cal):
                return None if x is None else bdays(trig, x, cal) > lim
            if disp is not None and late(disp, NOTICE_DISPATCH_BDAYS, nat) != late(disp, NOTICE_DISPATCH_BDAYS, both):
                continue
            if served is not None and late(served, NOTICE_SERVE_BDAYS, nat) != late(served, NOTICE_SERVE_BDAYS, both):
                continue
            if (disp and disp.weekday() >= 5) or (served and served.weekday() >= 5):
                continue
            nid += 1
            notice_rows.append(dict(notice_id=nid, account_id=a["id"], notice_type=rnd.choice(["DEMAND_NOTICE", "LEGAL_NOTICE"]), trigger_event="DPD_THRESHOLD", trigger_date=trig,
                                    dispatch_date=disp, served_date=served, dispatch_mode=rnd.choice(["REGISTERED_POST", "COURIER", "EMAIL"]), borrower_state=stt))
            if disp:
                ndoc += 1
                t["cn_core.notice_document"].append(dict(id=ndoc, notice_id=nid, document_version_no=1, is_latest_version=1, document_link=f"https://docs.example.test/notice/{nid}.pdf",
                                                         document_date=datetime.combine(disp, time(10, 0)), notice_reference_no=f"NR-{nid:07d}"))
            break
    t["compliance.notice"] += notice_rows

    # ================================================================ oracle ================================================================
    gaps, cnd = set(), set()
    # calls: canonical sessions only (mirrors never count)
    canon = [s for s in sessions if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
    per_contact_day = defaultdict(list)
    for s in canon:
        a = s["account"]["id"]
        d = s["start"].date()
        if not (WINDOW_START <= s["start"].timetz().replace(tzinfo=None) < pick(WINDOW_END, d)):
            gaps.add((a, "Q2"))
        per_contact_day[(a, s["contact"], d)].append(s)
        code = s["agent"]["employee_code"]
        if code is None:
            cnd.add((a, "Q6"))
        elif not any(vf <= d <= vt for vf, vt in emp_valid.get(code, [])):
            gaps.add((a, "Q6"))
    for (a, _, d), ss in per_contact_day.items():
        if len(ss) > pick(DAILY_CAP, d):
            gaps.add((a, "Q3"))
    for s in sessions:
        if s["direction"] != "OUTBOUND" or not s["connected"]:
            continue
        a = s["account"]["id"]
        stor, scen = s["_storage"], s["_scenario"]
        if stor == "NOT_FOUND":
            gaps.add((a, "Q7"))
            cnd.add((a, "Q4"))
        elif stor == "RETRIEVAL_FAILED":
            cnd.add((a, "Q7"))
            cnd.add((a, "Q4"))
        elif scen in ("no_transcript", "unclear"):
            cnd.add((a, "Q4"))
        elif scen in ("disclosure_first", "no_verification", "failed_then_disclosed"):
            gaps.add((a, "Q4"))
    for m in msgs:
        if m["status"] == "FAILED":
            continue
        ev = [c for c in consent_rows if c["contact_no"] == m["recip"] and c["channel"] == m["ch"] and c["effective_at"].replace(tzinfo=UTC) < m["ts"].astimezone(UTC)]
        granted = set()
        for c in sorted(ev, key=lambda c: c["effective_at"]):
            (granted.add if c["status"] == "GRANTED" else granted.discard)(c["purpose"])
        ok = m["cat"] in granted or (m["cat"] == "SERVICE" and "COLLECTIONS" in granted)
        if not ok:
            gaps.add((m["a"]["id"], "Q1"))
    for n in notice_rows:
        trig = n["trigger_date"]
        bad = (n["dispatch_date"] is None or bdays(trig, n["dispatch_date"], nat) > NOTICE_DISPATCH_BDAYS
               or n["served_date"] is None or bdays(trig, n["served_date"], nat) > NOTICE_SERVE_BDAYS)
        if bad:
            gaps.add((n["account_id"], "Q5"))
    # a question is a gap if any event is a gap, even when another event is undecidable
    cnd -= gaps

    # ------------------------------------------------------------ sample and request, gap key
    eligible = sorted(set(a["id"] for a in accts))
    sample_accts = rnd.sample([a for a in accts if a["id"] in eligible], SAMPLE)
    amb_nums = {x["account_number"] for x, _ in ambiguous}
    sample_refs = [a["account_number"] for a in sample_accts]
    for typo in ("CNF00000001", "CNF99999999", "CNH12"):
        sample_refs.insert(rnd.randrange(len(sample_refs)), typo)  # numbers that match nothing
    for x, _ in rnd.sample(ambiguous, 2):
        if x["account_number"] not in sample_refs:
            sample_refs.insert(rnd.randrange(len(sample_refs)), x["account_number"])  # reference matching two loans
    matched_ids = {a["id"] for a in sample_accts if a["account_number"] not in amb_nums}
    gk = ROOT / "eval" / "gap_keys"
    gk.mkdir(parents=True, exist_ok=True)
    qn = {"Q1": "consent_before_contact", "Q2": "calling_hours", "Q3": "calling_frequency", "Q4": "verification_before_disclosure", "Q5": "notice_timeline", "Q6": "agent_certification", "Q7": "recording_completeness"}
    key = sorted((a, q) for a, q in gaps if a in matched_ids)
    with (gk / "CN-01.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "question_ref", "check_type", "status"])
        w.writerows([[a, q, qn[q], "gap"] for a, q in key])
    with (gk / "CN-01_cannot_determine.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "question_ref", "check_type", "status"])
        w.writerows([[a, q, qn[q], "cannot_determine"] for a, q in sorted(cnd) if a in matched_ids])
    req = ROOT / "eval" / "requests"
    req.mkdir(parents=True, exist_ok=True)
    (req / "CN-01.txt").write_text(REQUEST.format(n=len(sample_refs), refs=", ".join(sample_refs)), encoding="utf-8")

    # ================================================================ load ================================================================
    order = ["uamdb.organization_type", "uamdb.organization", "uamdb.roles", "uamdb.users", "uamdb.user_role_link", "cn_core.customer", "cn_core.customer_contact_number",
             "cn_core.account", "cn_core.account_customer_contact_number", "cn_core.collection_case", "cn_core.disposition_group", "cn_core.disposition_code",
             "cn_core.tele_campaign", "cn_core.tele_process_type", "cn_core.tele_process_instance", "cn_core.tele_process_instance_user_link",
             "cn_core.tele_process_instance_call_logs", "cn_core.activity_log", "cn_core.tele_process_instance_activity", "cn_core.digital_template",
             "cn_core.communication_dashboard_t", "cn_core.notice_document", "compliance.dialer_config", "compliance.call_session_xref", "compliance.calling_policy_rule",
             "compliance.holiday_calendar", "compliance.customer_consent", "compliance.collector_certification", "compliance.call_recording",
             "compliance.call_transcript_segment", "compliance.notice"]
    for a in accts:
        t["cn_core.account"].append({k: v for k, v in a.items() if not k.startswith("_")})
    for c in custs:
        t["cn_core.customer"].append({k: v for k, v in c.items() if k != "state"})
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE " + ", ".join(order) + " RESTART IDENTITY CASCADE")
        for name in order:
            rows = t[name]
            if not rows:
                continue
            cols = list(rows[0])
            with conn.cursor().copy(f"COPY {name} ({', '.join(cols)}) FROM STDIN") as cp:
                for r in rows:
                    cp.write_row([r[c] for c in cols])
            print(f"  loaded {name:<46} {len(rows):>7,} rows")
        conn.commit()
    by_q = defaultdict(int)
    for _, q in key:
        by_q[q] += 1
    print(f"  request eval/requests/CN-01.txt: {len(sample_refs)} loan references ({len(sample_accts)} real, 3 unmatched, up to 2 ambiguous)")
    print(f"  gap key eval/gap_keys/CN-01.csv: {len(key)} true gaps in the matched sample: " + ", ".join(f"{q}={n}" for q, n in sorted(by_q.items())))
    print(f"  cannot-determine key: {len([1 for a, q in cnd if a in matched_ids])} (account x question)")


REQUEST = """Subject: Audit request CO-04 - outsourced collections, FY26 sample

From: Internal Audit, Example Lender Ltd (synthetic request)

Please provide evidence for the {n} sampled loan accounts listed below (by loan account number), covering January to October 2026.

Q1. For every WhatsApp or SMS message sent, show that the borrower had given consent before it was sent.
Q2. Confirm that every collection call was made within the permitted calling hours.
Q3. Confirm that no contact number was called more often than the permitted daily frequency.
Q4. Where dues were disclosed on a call, show the borrower's identity was verified before disclosure.
Q5. Show that notices were dispatched and served within the permitted timeline.
Q6. Confirm the recovery agent was certified on the date of each call they made.
Q7. Provide the recording for every connected call.

Severity scale for gaps:
  Critical - regulatory breach affecting the borrower directly (Q1, Q2, Q3, Q4)
  Major    - process breach with documentary impact (Q5, Q6)
  Minor    - evidence completeness (Q7)

Sampled accounts:
{refs}
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    main(ap.parse_args().seed)
