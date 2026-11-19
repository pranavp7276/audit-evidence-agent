"""Build the common sandbox "CN book" (datasets D1 to D13) in the CN Core replica, and the ground truth for the CO-04 checks.

Structure: db/migrations/V005 and V009 (table names are CN Core's; the `book` schema exposes the sandbox's own D1..D13 field names).
Proposed volumes at --scale 1.0: 100,000 delinquent accounts, 85,000 borrowers, 3 lenders (a bank, an NBFC, an MFI), 12 months of history,
1.2M repayment rows, 3M contact attempts, 60,000 transcribed calls, 150,000 promises, 400,000 payments, 20,000 borrowers' bank statements,
85,000 bureau snapshots a month, 85,000 consent/DND records, 400 templates, about 200 policy documents.
The default --scale 0.1 keeps every ratio and fits a small database; use 1.0 only on a database sized for ~6 million rows.

All data is synthetic. Problems are seeded at random; the gap key comes from an independent implementation of the rules over the generated
rows, not from the platform's checks. Two dialers on purpose: SlashRTC logs times in IST, CognifAI in UTC. D12 differs by lender and some
rules change over time.

  python scripts/gen_book.py [--scale 0.1] [--seed 11]      replaces the data in DATABASE_URL (needs ALLOW_RELOAD=1 on a shared database)
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import shutil
import tempfile
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
IST = timezone(timedelta(hours=5, minutes=30))
AS_OF = date(2026, 11, 19)
START, END = date(2025, 11, 3), date(2026, 10, 29)  # 12 months of history
MONTHS = [(2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 11)]
EPOCH = date(2025, 1, 1)

# ---------------------------------------------------------------------------- lenders and their D12 rules (re-stated independently in the oracle)
LENDERS = [("BANK01", "Sahyadri Bank", "BANK", 0.45), ("NBFC01", "Kaveri Finserv", "NBFC", 0.35), ("MFI01", "Ganga Microfinance", "MFI", 0.20)]
WINDOW_START = {"BANK01": time(8, 0), "NBFC01": time(8, 0), "MFI01": time(9, 0)}
WINDOW_END = {"BANK01": [(EPOCH, date(2026, 4, 1), time(19, 0)), (date(2026, 4, 1), None, time(18, 50))],
              "NBFC01": [(EPOCH, None, time(19, 0))], "MFI01": [(EPOCH, None, time(18, 0))]}
DAILY_CAP = {"BANK01": [(EPOCH, date(2026, 6, 1), 4), (date(2026, 6, 1), None, 5)], "NBFC01": [(EPOCH, None, 3)], "MFI01": [(EPOCH, None, 2)]}
NOTICE_DISPATCH_BDAYS, NOTICE_SERVE_BDAYS = 3, 7
NATIONAL_HOLIDAYS = {
    date(2025, 11, 5): "Guru Nanak Jayanti", date(2025, 12, 25): "Christmas", date(2026, 1, 26): "Republic Day", date(2026, 3, 4): "Holi",
    date(2026, 4, 3): "Good Friday", date(2026, 8, 15): "Independence Day", date(2026, 10, 2): "Gandhi Jayanti", date(2026, 11, 8): "Diwali",
    date(2026, 12, 25): "Christmas", date(2027, 1, 26): "Republic Day"}
STATE_HOLIDAYS = [(date(2026, 1, 15), "Pongal", "TN"), (date(2026, 5, 1), "Maharashtra Day", "MH"), (date(2026, 8, 26), "Onam", "KL"),
                  (date(2026, 11, 1), "Karnataka Rajyotsava", "KA"), (date(2025, 11, 1), "Karnataka Rajyotsava", "KA")]

CITIES = [("Mumbai", "MH", "mr"), ("Pune", "MH", "mr"), ("Bengaluru", "KA", "kn"), ("Mysuru", "KA", "kn"), ("Chennai", "TN", "ta"), ("Coimbatore", "TN", "ta"),
          ("Hyderabad", "TS", "te"), ("Vijayawada", "AP", "te"), ("Delhi", "DL", "hi"), ("Lucknow", "UP", "hi"), ("Jaipur", "RJ", "hi"), ("Kolkata", "WB", "en")]
PRODUCTS = {"BANK": [("PL", "Personal loan", 50_000, 1_000_000), ("BL", "Business loan", 100_000, 2_000_000), ("CC", "Credit card", 20_000, 300_000)],
            "NBFC": [("TW", "Two-wheeler loan", 40_000, 150_000), ("CD", "Consumer durable loan", 10_000, 80_000), ("BL", "Business loan", 100_000, 1_000_000)],
            "MFI": [("JLG", "Group micro-loan", 20_000, 60_000), ("IL", "Individual micro-loan", 25_000, 75_000)]}
FIRST = ["Aarav", "Vivaan", "Aditya", "Rohan", "Arjun", "Karthik", "Sandeep", "Imran", "Suresh", "Manoj", "Ravi", "Anil", "Sunil", "Vikram", "Ajay", "Rahul", "Harish", "Gopal",
         "Diya", "Ananya", "Isha", "Kavya", "Meera", "Neha", "Pooja", "Farah", "Lakshmi", "Sunita", "Priya", "Deepa", "Rekha", "Sneha", "Nisha", "Jyoti", "Usha", "Bhavna"]
LAST = ["Sharma", "Iyer", "Reddy", "Patel", "Khan", "Nair", "Gupta", "Singh", "Das", "Joshi", "Menon", "Verma", "Rao", "Chopra", "Pillai", "Naidu", "Gowda", "Kulkarni", "Yadav", "Banerjee"]
OCCUPATIONS = ["SALARIED", "SELF_EMPLOYED", "DAILY_WAGE", "FARMER", "SMALL_TRADER", "HOMEMAKER", "GIG_WORKER"]
PHONE_SOURCES = ["LOS", "BUREAU", "FIELD_VISIT", "CUSTOMER_APP", "DIALER_CAPTURE", "REFERENCE"]

# transcript phrase banks: greeting, identity request, identity answer, dues disclosure, promise, closing, unclear (language tag per turn)
BANK = {
    "en": ["Hello, I am calling from {agency} about your loan.", "Please confirm your date of birth.", "My date of birth is {dob}.", "Your instalment of {amt} rupees is overdue.",
           "I will pay next week.", "Thank you."],
    "hi": ["नमस्ते, मैं {agency} से बोल रहा हूँ।", "कृपया अपनी जन्म तिथि बताइए।", "मेरी जन्म तिथि {dob} है।", "आपकी {amt} रुपये की किस्त बकाया है।", "मैं अगले हफ्ते भुगतान कर दूँगा।", "धन्यवाद।"],
    "kn": ["ನಮಸ್ಕಾರ, ನಾನು {agency} ಇಂದ ಮಾತನಾಡುತ್ತಿದ್ದೇನೆ.", "ದಯವಿಟ್ಟು ನಿಮ್ಮ ಜನ್ಮ ದಿನಾಂಕ ತಿಳಿಸಿ.", "ನನ್ನ ಜನ್ಮ ದಿನಾಂಕ {dob}.", "ನಿಮ್ಮ {amt} ರೂಪಾಯಿ ಕಂತು ಬಾಕಿ ಇದೆ.",
           "ನಾನು ಮುಂದಿನ ವಾರ ಪಾವತಿಸುತ್ತೇನೆ.", "ಧನ್ಯವಾದಗಳು."],
    "ta": ["வணக்கம், நான் {agency}-இல் இருந்து பேசுகிறேன்.", "உங்கள் பிறந்த தேதியை சொல்லுங்கள்.", "என் பிறந்த தேதி {dob}.", "உங்கள் {amt} ரூபாய் தவணை நிலுவையில் உள்ளது.",
           "நான் அடுத்த வாரம் செலுத்துகிறேன்.", "நன்றி."],
    "te": ["నమస్కారం, నేను {agency} నుండి మాట్లాడుతున్నాను.", "దయచేసి మీ పుట్టిన తేదీ చెప్పండి.", "నా పుట్టిన తేదీ {dob}.", "మీ {amt} రూపాయల వాయిదా బకాయి ఉంది.",
           "నేను వచ్చే వారం చెల్లిస్తాను.", "ధన్యవాదాలు."],
    "hi-en": ["Namaste, main {agency} se bol raha hoon.", "Please apni date of birth bataiye.", "Meri DOB {dob} hai.", "Aapki {amt} rupees ki EMI overdue hai.",
              "Main next week pay kar dunga.", "Thank you."],
}
REMINDER = {"en": "Your instalment of Rs {{amount}} is due on {{due_date}}. Pay here: {{link}}",
            "hi": "आपकी {{amount}} रुपये की किस्त {{due_date}} को बकाया है। भुगतान करें: {{link}}",
            "kn": "ನಿಮ್ಮ {{amount}} ರೂಪಾಯಿ ಕಂತು {{due_date}} ರಂದು ಬಾಕಿ ಇದೆ. ಪಾವತಿಸಿ: {{link}}",
            "ta": "உங்கள் {{amount}} ரூபாய் தவணை {{due_date}} அன்று நிலுவையில் உள்ளது. செலுத்த: {{link}}",
            "te": "మీ {{amount}} రూపాయల వాయిదా {{due_date}} నాడు బకాయి ఉంది. చెల్లించండి: {{link}}",
            "mr": "तुमचा {{amount}} रुपयांचा हप्ता {{due_date}} रोजी थकीत आहे. भरा: {{link}}"}
CATEGORY_TEXT = {"COLLECTIONS": REMINDER, "SERVICE": {k: "We received your payment of Rs {{amount}} on {{pay_date}}. Thank you." if k == "en" else REMINDER[k] for k in REMINDER},
                 "PROMOTIONAL": {k: "You have a pre-approved offer on your next loan. Know more: {{link}}" if k == "en" else REMINDER[k] for k in REMINDER}}


def pick(rules, d):
    for a, b, v in rules:
        if a <= d and (b is None or d < b):
            return v
    raise ValueError(d)


def bdays(start: date, end: date, hol: set[date]) -> int:
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


class Sink:
    """Streams rows to one CSV file per table (so the full volume never sits in memory) and loads them with COPY."""

    def __init__(self, conn, tmp: Path):
        self.conn, self.tmp, self.cols, self.writers, self.files, self.counts = conn, tmp, {}, {}, {}, defaultdict(int)

    def _open(self, table: str):
        self.cols[table] = [r[0] for r in self.conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position", table.split("."))]
        if not self.cols[table]:
            raise SystemExit(f"Table {table} does not exist: run scripts/migrate.py first.")
        f = (self.tmp / (table + ".csv")).open("w", newline="", encoding="utf-8")
        self.files[table], self.writers[table] = f, csv.writer(f)

    def add(self, table: str, **row) -> None:
        if table not in self.writers:
            self._open(table)
        extra = set(row) - set(self.cols[table])
        if extra:
            raise KeyError(f"{table} has no column(s) {sorted(extra)}")
        self.writers[table].writerow([r"\N" if row.get(c) is None else row[c] for c in self.cols[table]])
        self.counts[table] += 1

    def load(self, order: list[str]) -> None:
        for f in self.files.values():
            f.close()
        for table in order:
            if table not in self.files:
                continue
            with (self.tmp / (table + ".csv")).open("rb") as fh, self.conn.cursor().copy(
                    f"COPY {table} ({', '.join(self.cols[table])}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
                while chunk := fh.read(1 << 20):
                    cp.write(chunk)
            print(f"  loaded {table:<46} {self.counts[table]:>10,} rows")


def main(scale: float, seed: int) -> None:
    load_dotenv(ROOT / ".env")
    url = os.environ.get("DATABASE_URL", "")
    host = url.split("@")[-1].split("/")[0].split(":")[0]
    if host not in ("localhost", "127.0.0.1", "db", "") and os.environ.get("ALLOW_RELOAD") != "1":
        raise SystemExit(f"Refusing to reload the shared database at {host}: this replaces everyone's data. Set ALLOW_RELOAD=1 only if the team agreed.")
    rnd = random.Random(seed)
    nat = set(NATIONAL_HOLIDAYS)
    n_acc, n_borr = max(int(100_000 * scale), 600), max(int(85_000 * scale), 500)
    n_agents = max(120, int(1_200 * scale))
    tmp = Path(tempfile.mkdtemp(prefix="book-"))
    print(f"Generating the book at scale {scale}: {n_acc:,} accounts, {n_borr:,} borrowers, {n_agents} collectors (seed {seed})")

    with psycopg.connect(url) as conn:
        S = Sink(conn, tmp)
        add = S.add

        # ================================================================ UAMDB: lenders, agencies, users
        for i, c, n, cat in [(1, "LENDER", "Lender", "INTERNAL"), (2, "TELE_AGENCY", "Tele-calling agency", "AGENCY"), (3, "FIELD_AGENCY", "Field agency", "AGENCY")]:
            add("uamdb.organization_type", organization_type_id=i, organization_type_code=c, organization_type_name=n, organization_type_category=cat,
                authentication_type="SSO" if i == 1 else "PASSWORD", two_factor_auth="Y" if i == 1 else "N", organization_type_desc=n)
        orgs = [(1, "BANK01", "Sahyadri Bank", 1), (2, "NBFC01", "Kaveri Finserv", 1), (3, "MFI01", "Ganga Microfinance", 1), (11, "APEX", "Apex Tele Services", 2),
                (12, "NSTAR", "Northstar BPO", 2), (13, "MERID", "Meridian Voice", 2), (14, "SUNRS", "Sunrise Contact Centre", 2), (21, "FLD01", "Pioneer Field Recovery", 3),
                (22, "FLD02", "Delta Field Services", 3)]
        for oid, code, name, ot in orgs:
            city, st, _ = rnd.choice(CITIES)
            add("uamdb.organization", organization_id=oid, organization_code=code, organization_name=name, organization_type_id=ot, registered_address=f"{rnd.randint(1, 99)} Business Park",
                registered_contact_no=f"022{rnd.randint(10000000, 99999999)}", organization_email=f"ops@{code.lower()}.example", city=city, state=st,
                postal_code=str(rnd.randint(400000, 600000)), country="IN", contact_person_name="Operations Manager", contact_person_designation="Manager",
                contact_person_contact_no=f"98{rnd.randint(10000000, 99999999)}", organization_status="ACTIVE")
        TELE = (11, 12, 13, 14)
        for rid, name, oid, rt in [(1, "Collections Admin", 1, "ADMIN"), (2, "Tele Agent", 11, "TELE"), (3, "Tele Supervisor", 11, "TELE"), (4, "Compliance Officer", 1, "COMPLIANCE"), (5, "Field Agent", 21, "FIELD")]:
            add("uamdb.roles", role_id=rid, role_name=name, role_description=name, organization_id=oid, role_type=rt, admin_role_flag="Y" if rid == 1 else "N", super_admin_role_flag="N")
        users, agents_by_org, supervisors, uid, emp = [], defaultdict(list), {}, 0, 10000

        def add_user(org, role, desig, code=True, dept="Collections"):
            nonlocal uid, emp
            uid += 1
            emp += 1
            fn, ln = rnd.choice(FIRST), rnd.choice(LAST)
            u = dict(user_id=uid, user_name=f"{fn.lower()}.{ln.lower()}{uid}", organization_id=org, first_name=fn, last_name=ln, role_id=role, designation=desig, department=dept,
                     employee_code=f"EMP{emp}" if code else None, base_branch_code=f"BR{rnd.randint(1, 20):03d}", contact_no=f"9{rnd.randint(100000000, 999999999)}",
                     email=f"user{uid}@example.test", city=rnd.choice(CITIES)[0], country="IN", gender=rnd.choice(["M", "F"]), preferred_language=rnd.choice(["en", "hi", "kn", "ta"]), user_status="ACTIVE")
            add("uamdb.users", **u)
            add("uamdb.user_role_link", user_role_link_id=uid, user_id=uid, role_id=role)
            users.append(u)
            return u
        for _ in range(5):
            add_user(1, 4, "Compliance Officer", dept="Compliance")
        for _ in range(3):
            add_user(1, 1, "Collections Admin", dept="Operations")
        for oid in TELE:
            supervisors[oid] = [add_user(oid, 3, "Tele Supervisor") for _ in range(2)]
        for k in range(n_agents):
            oid = TELE[k % 4]
            agents_by_org[oid].append(add_user(oid, 2, "Tele Agent", code=rnd.random() > 0.02))
        all_agents = [a for v in agents_by_org.values() for a in v]

        # ================================================================ lenders, branches
        for code, name, typ, _ in LENDERS:
            add("cn_core.institution", institution_code=code, institution_name=name, lender_type=typ)
            add("cn_core.lender", lender_name=name, institution_code=code, lender_type=typ)
        branches = defaultdict(list)
        for code, *_ in LENDERS:
            for i, (city, st, _) in enumerate(CITIES * 2):
                bc = f"{code[:2]}{len(branches[code]) + 1:03d}"
                branches[code].append((bc, city, st))
                add("cn_core.branch", branch_code=bc, branch_name=f"{city} {i % 2 + 1}", branch_address=f"{rnd.randint(1, 200)} Main Road", city_code=city[:3].upper(), state_code=st,
                    postal_code=str(rnd.randint(400000, 700000)), country_code="IN", city=city, institution_code=code)

        # ================================================================ dialers, campaigns, process types and instances (12 months)
        add("compliance.dialer_config", dialer_code="SLASHRTC", dialer_name="SlashRTC", timezone="Asia/Kolkata", session_id_format="SRTC-YYYYMMDD-NNNNNN")
        add("compliance.dialer_config", dialer_code="COGNIFAI", dialer_name="CognifAI", timezone="UTC", session_id_format="cgn-<uuid>")
        dialer_tz = {"SLASHRTC": IST, "COGNIFAI": UTC}
        agency_dialers = {11: {"MANUAL": "SLASHRTC", "CAMPAIGN": "SLASHRTC"}, 12: {"MANUAL": "SLASHRTC", "CAMPAIGN": "SLASHRTC"},
                          13: {"MANUAL": "COGNIFAI", "CAMPAIGN": "COGNIFAI"}, 14: {"MANUAL": "SLASHRTC", "CAMPAIGN": "COGNIFAI"}}
        agency_name = {oid: name for oid, _, name, _ in orgs}
        pinst, tid, iid = {}, 0, 0
        for oid in TELE:
            add("cn_core.tele_campaign", id=oid, tele_campaign_name=f"{agency_name[oid]} collections", campaign_owner_id=supervisors[oid][0]["user_id"], campaign_status="A", created_date=datetime(2025, 10, 1))
            for mode in ("MANUAL", "CAMPAIGN"):
                tid += 1
                d = agency_dialers[oid][mode]
                add("cn_core.tele_process_type", id=tid, process_type_name=f"{agency_name[oid]} {mode.title()}", process_type_mode=mode, campaign_id=oid, process_type_status="ACTIVE",
                    calling_ratio=1 if mode == "MANUAL" else 3, dialer_process_id=9000 + tid, wait_time=30, times_to_try=3, sticky_agent_flag=0, inbound_delay_time=10,
                    process_call_attempts=3, process_max_calls_per_day=5, created_date=date(2025, 10, 1), dialer_code=d)
                for y, m in MONTHS:
                    iid += 1
                    pinst[(oid, mode, y, m)] = iid
                    add("cn_core.tele_process_instance", id=iid, process_type_id=tid, process_name=f"{agency_name[oid]} {mode.title()} {y}-{m:02d}", process_mode=mode, campaign_id=oid,
                        process_status="COMPLETED", calling_ratio=1 if mode == "MANUAL" else 3, dialer_process_id=9000 + tid, process_start_date=date(y, m, 1),
                        process_start_time=datetime(y, m, 1, 8, 0), process_end_date=date(y, m, 28), process_end_time=datetime(y, m, 28, 19, 0), number_of_accounts=0,
                        number_of_agents=len(agents_by_org[oid]), supervisor_id=supervisors[oid][0]["user_id"], dialer_code=d)
        link = 0
        for oid, ags in agents_by_org.items():
            for a in ags:
                link += 1
                add("cn_core.tele_process_instance_user_link", id=link, tele_process_instance_id=pinst[(oid, "MANUAL", 2025, 11)], user_id=a["user_id"], user_group_id=oid)

        # ================================================================ D12 rules (per lender, effective-dated), holidays, notice limits
        rid = 0

        def rule(code, key, val, unit, frm, to, **kw):
            nonlocal rid
            rid += 1
            add("compliance.calling_policy_rule", rule_id=rid, policy_code="D12", rule_key=key, rule_value=val, unit=unit, effective_from=frm, effective_to=to, institution_code=code,
                counting_unit=kw.get("cu"), counting_rule=kw.get("cr"), note=kw.get("note"))
        for code, *_ in LENDERS:
            rule(code, "calling_window_start", f"{WINDOW_START[code]:%H:%M}", "local_time", EPOCH, None, note="Borrower local time (IST); inclusive")
            for a, b, v in WINDOW_END[code]:
                rule(code, "calling_window_end", f"{v:%H:%M}", "local_time", a, b, note="Borrower local time (IST); exclusive")
            for a, b, v in DAILY_CAP[code]:
                rule(code, "max_attempts_per_contact_per_day", str(v), "attempts", a, b, cu="CONTACT_NUMBER",
                     cr="Distinct outbound call sessions to the same contact number on one IST calendar day; excludes SYSTEM_FAILURE; a session mirrored across dialers counts once")
        rule(None, "notice_dispatch_sla_business_days", str(NOTICE_DISPATCH_BDAYS), "business_days", EPOCH, None, note="Trigger date to dispatch; Mon-Fri excluding national holidays; day N inclusive")
        rule(None, "notice_service_sla_business_days", str(NOTICE_SERVE_BDAYS), "business_days", EPOCH, None, note="Trigger date to service; same calendar; day N inclusive")
        hid = 0
        for d, n in sorted(NATIONAL_HOLIDAYS.items()):
            hid += 1
            add("compliance.holiday_calendar", holiday_id=hid, holiday_date=d, holiday_name=n, scope="national")
        for d, n, st in sorted(STATE_HOLIDAYS):
            hid += 1
            add("compliance.holiday_calendar", holiday_id=hid, holiday_date=d, holiday_name=n, scope="state", state=st)

        # ================================================================ D11 template registry (400)
        templates = defaultdict(list)  # (channel, category) -> approved template ids
        for t in range(1, 401):
            channel = rnd.choices(["WHATSAPP", "SMS", "EMAIL"], [0.4, 0.4, 0.2])[0]
            cat = rnd.choices(["COLLECTIONS", "SERVICE", "PROMOTIONAL"], [0.55, 0.25, 0.20])[0]
            lang = rnd.choices(["en", "hi", "kn", "ta", "te", "mr"], [0.3, 0.25, 0.15, 0.1, 0.1, 0.1])[0]
            status = rnd.choices(["APPROVED", "PENDING", "REJECTED", "EXPIRED"], [0.88, 0.04, 0.04, 0.04])[0]
            add("cn_core.digital_template", template_id=t, sms_category=cat, sms_dlt_id=f"DLT{1000 + t}", digital_channel=channel, template_subject=f"{cat.title()} {lang} v{t % 5 + 1}",
                template_body=CATEGORY_TEXT[cat][lang], language=lang, approval_status=status)
            if status == "APPROVED":
                templates[(channel, cat, lang)].append(t)

        def template_for(channel, cat, lang):
            for key in ((channel, cat, lang), (channel, cat, "en")):
                if templates.get(key):
                    return rnd.choice(templates[key])
            return rnd.choice([v for k, vs in templates.items() if k[0] == channel and k[1] == cat for v in vs])

        # ================================================================ D2 borrowers, D1 accounts
        used_nums, cust_rows, ccn = set(), [], defaultdict(list)
        cc_id = addr_id = email_id = variant_id = 0

        def mobile():
            while True:
                n = f"{rnd.choice('6789')}{rnd.randint(100000000, 999999999)}"
                if n not in used_nums:
                    used_nums.add(n)
                    return n
        lender_pick = [c for c, *_ in LENDERS]
        lender_w = [w for *_, w in LENDERS]
        for i in range(1, n_borr + 1):
            cid = 5_000_000 + i
            lender = rnd.choices(lender_pick, lender_w)[0]
            city, st, lang = rnd.choice(CITIES)
            fn, ln = rnd.choice(FIRST), rnd.choice(LAST)
            name = f"{fn} {ln}"
            deceased = rnd.random() < 0.005
            cust = dict(id=cid, institution_code=lender, source_system_code="LMS", customer_number=f"C{rnd.randint(10**8, 10**9 - 1)}", unified_customer_id=f"U{cid}", customer_name=name,
                        customer_first_name=fn, customer_last_name=ln, father_name=f"{rnd.choice(FIRST)} {ln}", customer_status_id=1, gender_code="F" if FIRST.index(fn) >= 18 else "M",
                        customer_category_code="I", customer_type_code="INDIVIDUAL", branch_code=rnd.choice(branches[lender])[0], occupation=rnd.choice(OCCUPATIONS),
                        preferred_language_code=lang, open_date=date(2022, 1, 1) + timedelta(days=rnd.randint(0, 1200)), birth_date=date(1962, 1, 1) + timedelta(days=rnd.randint(0, 14500)),
                        deceased_flag="Y" if deceased else "N", deceased_date=date(2026, rnd.randint(1, 9), rnd.randint(1, 28)) if deceased else None)
            add("cn_core.customer", **cust)
            cust.update(state=st, city=city, name=name)
            cust_rows.append(cust)
            for seq, typ in enumerate(["PRIMARY"] + ["ALTERNATE"] * (rnd.random() < 0.45) + ["REFERENCE"] * (rnd.random() < 0.12), 1):
                cc_id += 1
                row = dict(id=cc_id, customer_id=cid, category="MOBILE", sequence_no=seq, contact_type=typ, contact_no=mobile(), contact_number_type="MOBILE", isd_code="91",
                           contact_name=name, verified_status=rnd.choice(["VERIFIED", "UNVERIFIED"]), source=rnd.choice(PHONE_SOURCES),
                           captured_date=date(2022, 1, 1) + timedelta(days=rnd.randint(0, 1400)))
                add("cn_core.customer_contact_number", **row)
                ccn[cid].append(row)
            if rnd.random() < 0.6:
                email_id += 1
                add("cn_core.customer_email", id=email_id, customer_id=cid, category="EMAIL", sequence_no=1, email_type=rnd.choice(["PERSONAL", "WORK"]),
                    email=f"{fn.lower()}.{ln.lower()}{rnd.randint(1, 999)}@example.test", verified_status=rnd.choice(["VERIFIED", "UNVERIFIED"]))
            for seq in range(1, 1 + 1 + (rnd.random() < 0.3)):
                addr_id += 1
                add("cn_core.customer_address", id=addr_id, customer_id=cid, category="ADDRESS", sequence_no=seq, address_type="RESIDENCE" if seq == 1 else "OFFICE",
                    address_line_1=f"{rnd.randint(1, 400)}, {rnd.choice(['MG Road', 'Gandhi Nagar', 'Temple Street', 'Station Road', 'Lake View'])}",
                    address_line_2=f"{rnd.choice(['Ward', 'Sector', 'Block'])} {rnd.randint(1, 30)}", city=city, state=st, postal_code=str(rnd.randint(400000, 700000)),
                    landmark=rnd.choice(["Near temple", "Near bus stand", "Opp. school", None]))
            if rnd.random() < 0.3:
                for vtype, vname in rnd.sample([("INITIAL", f"{fn[0]}. {ln}"), ("REORDERED", f"{ln} {fn}"), ("SPELLING", f"{fn[:-1]}{rnd.choice('aeiy')} {ln}")], rnd.randint(1, 2)):
                    variant_id += 1
                    add("cn_core.customer_name_variant", id=variant_id, customer_id=cid, variant_name=vname, variant_type=vtype)
        by_lender = defaultdict(list)
        for c in cust_rows:
            by_lender[c["institution_code"]].append(c)

        accts, seen_nums = [], set()
        bucket_w = [("0-30", 0.35), ("31-60", 0.25), ("61-90", 0.18), ("90+", 0.22)]
        for i in range(1, n_acc + 1):
            cust = cust_rows[i - 1] if i <= n_borr else rnd.choice(cust_rows)  # every borrower has a loan; the rest are second loans
            lender = cust["institution_code"]
            typ = next(t for c, _, t, _ in LENDERS if c == lender)
            prod, pname, lo, hi = rnd.choice(PRODUCTS[typ])
            loan = round(rnd.uniform(lo, hi) / 1000) * 1000
            bucket = rnd.choices([b for b, _ in bucket_w], [w for _, w in bucket_w])[0]
            dpd = {"0-30": rnd.randint(1, 30), "31-60": rnd.randint(31, 60), "61-90": rnd.randint(61, 90), "90+": rnd.randint(91, 300)}[bucket]
            tenure = rnd.choice([12, 18, 24]) if typ == "MFI" else rnd.choice([12, 24, 36, 48, 60])
            emi = round(loan * (1 + 0.14 * tenure / 12) / tenure)
            while True:
                pre = {"BANK": "SB", "NBFC": "KF", "MFI": "GM"}[typ]
                num = f"{pre}{rnd.randint(10**9, 10**10 - 1)}"
                if num not in seen_nums:
                    seen_nums.add(num)
                    break
            br = next((b for b in branches[lender] if b[1] == cust["city"]), branches[lender][0])
            cycle = rnd.randint(1, 28)
            a = dict(id=7_000_000 + i, institution_code=lender, source_system_code="LMS", account_number=num, account_type_code="LN", customer_id=cust["id"], branch_code=br[0],
                     product_category_code="RETAIL", product_segment_code=prod, product_group_code="UNSECURED", product_code=prod, account_status_id=1, loan_amount=loan,
                     sanctioned_amount=loan, disbursed_amount=loan, open_date=date(2023, 1, 1) + timedelta(days=rnd.randint(0, 900)),
                     disbursal_date=date(2023, 1, 5) + timedelta(days=rnd.randint(0, 900)), maturity_date=date(2027, 1, 1) + timedelta(days=rnd.randint(0, 1200)), tenure=tenure,
                     interest_rate=round(rnd.uniform(11, 26), 5), installment_amount=emi, repayment_cycle_day=cycle, due_date=date(2026, 10, cycle), next_due_date=date(2026, 11, cycle),
                     principal_outstanding_amount=round(loan * rnd.uniform(.3, .9)), interest_outstanding_amount=round(loan * .03), total_outstanding_amount=round(loan * rnd.uniform(.4, 1.0)),
                     total_overdue_amount=round(emi * dpd / 30), dpd=dpd, delinquency_bucket_code=bucket, last_payment_received_date=datetime(2025, 11, 1) + timedelta(days=rnd.randint(0, 300)),
                     last_payment_received_amount=emi, npa_flag="Y" if dpd > 90 else "N", overdue_since_date=date(2026, 10, 31) - timedelta(days=dpd), city=cust["city"],
                     restructured_flag="Y" if rnd.random() < 0.06 else "N", settlement_flag="Y" if rnd.random() < 0.03 else "N", legal_flag="Y" if dpd > 120 and rnd.random() < 0.25 else "N")
            add("cn_core.account", **a)
            a["_cust"], a["_emi"], a["_typ"] = cust, emi, typ
            accts.append(a)
        # the same loan number under two lenders: references to it are ambiguous
        ambiguous = []
        pool = defaultdict(list)
        for a in accts:
            pool[a["institution_code"]].append(a)
        # (numbers are already written to the stream, so duplicates are produced by re-issuing a second account row under another lender)
        for x in rnd.sample(pool["BANK01"], 6) + rnd.sample(pool["NBFC01"], 6):
            other = "NBFC01" if x["institution_code"] == "BANK01" else "MFI01"
            y = rnd.choice(pool[other])
            ambiguous.append((x, y))
        for x, y in ambiguous:  # the stored row is patched by an UPDATE after the load; later code (the sample) must see the shared number
            y["account_number"] = x["account_number"]
        acct_by_id = {a["id"]: a for a in accts}

        # D3 repayment schedule: 12 monthly instalments per account, the recent ones unpaid according to DPD
        aps = 0
        for a in accts:
            k_unpaid = min(12, max(1, -(-a["dpd"] // 30)))
            cust = a["_cust"]
            for j, (y, m) in enumerate(MONTHS):
                aps += 1
                due = date(y, m, min(a["repayment_cycle_day"], 28))
                interest = round(a["_emi"] * 0.28)
                unpaid = j >= 12 - k_unpaid
                paid, pdate, mode, bounce = None, None, None, None
                if not unpaid:
                    paid = a["_emi"] if rnd.random() > 0.1 else round(a["_emi"] * rnd.uniform(0.5, 0.9))
                    pdate = due + timedelta(days=rnd.choice([0, 0, 0, 1, 2, 3, 5, 9]))
                    mode = rnd.choices(["NACH", "UPI", "PAYMENT_LINK", "CASH", "CARD"], [0.35, 0.35, 0.15, 0.1, 0.05])[0]
                elif rnd.random() < 0.3:
                    bounce = rnd.choice(["INSUFFICIENT_FUNDS", "MANDATE_REJECTED", "ACCOUNT_CLOSED", "SIGNATURE_MISMATCH"])
                    mode = "NACH"
                add("cn_core.account_payment_schedule", id=aps, account_id=a["id"], due_type="EMI", due_date=due, due_amount=a["_emi"], principal_due_amount=a["_emi"] - interest,
                    interest_due_amount=interest, amount_paid=paid, paid_date=pdate, payment_mode=mode, bounce_reason=bounce)
        acc_cc = case = 0
        case_agent = {}
        for a in accts:
            for r in ccn[a["customer_id"]]:
                acc_cc += 1
                add("cn_core.account_customer_contact_number", id=acc_cc, account_id=a["id"], customer_id=a["customer_id"], category=r["category"], sequence_no=r["sequence_no"],
                    contact_type=r["contact_type"], contact_no=r["contact_no"], contact_number_type="MOBILE", isd_code="91", contact_name=r["contact_name"])
            case += 1
            oid = rnd.choice(TELE)
            ag = rnd.choice(agents_by_org[oid])
            case_agent[a["id"]] = (oid, ag)
            add("cn_core.collection_case", id=8_000_000 + case, case_year=2026, case_month=1, case_start_date=datetime(2025, 11, 1), collection_status="ACTIVE", resolution_status="OPEN",
                account_id=a["id"], case_owner_user_id=supervisors[oid][0]["user_id"], allocated_tele_call_user_id=ag["user_id"], allocated_tele_call_agency_id=oid,
                allocated_tele_call_agency_user_id=supervisors[oid][0]["user_id"], case_start_dpd=a["dpd"], dpd=a["dpd"], delinquency_bucket_code=a["delinquency_bucket_code"],
                total_outstanding_amount=a["total_outstanding_amount"], case_status_id=1)
        for g, n in [("CONTACT", "Contacted"), ("NOCONTACT", "Not contacted"), ("PROMISE", "Promise to pay")]:
            add("cn_core.disposition_group", disposition_group_code=g, disposition_group_name=n)
        for c, n, g in [("PTP", "Promise to pay", "PROMISE"), ("RTP", "Refused to pay", "CONTACT"), ("CALLBACK", "Call back", "CONTACT"), ("WRONGNO", "Wrong number", "NOCONTACT"), ("NOANS", "No answer", "NOCONTACT")]:
            add("cn_core.disposition_code", disposition_code=c, disposition_code_name=n, disposition_group_code=g, disposition_level="1", sub_disposition_label_name=n)

        # ================================================================ D4 contact history: calls
        n_days = (END - START).days
        sess_n = [0]
        ta_set = {a["id"] for a in accts if rnd.random() < 0.12}  # accounts whose calls are transcribed (D5: about 5% of calls overall)

        def local_dt(d: date, h: int, m: int, s: int = 0) -> datetime:
            return datetime.combine(d, time(h, m, s), tzinfo=IST)

        def new_sid(dialer: str, ts: datetime) -> str:
            sess_n[0] += 1
            return f"SRTC-{ts:%Y%m%d}-{sess_n[0]:07d}" if dialer == "SLASHRTC" else "cgn-" + str(uuid.UUID(int=rnd.getrandbits(128)))[:23]

        def make_session(a, contact, start, forced=None, direction="OUTBOUND"):
            oid, ag = case_agent[a["id"]]
            if rnd.random() < 0.1:
                oid = rnd.choice(TELE)
                ag = rnd.choice(agents_by_org[oid])
            mode = rnd.choices(["MANUAL", "CAMPAIGN"], [0.45, 0.55])[0]
            dialer = agency_dialers[oid][mode]
            status = forced or rnd.choices(["CONNECTED", "NO_ANSWER", "BUSY", "SYSTEM_FAILURE"], [0.5, 0.33, 0.12, 0.05])[0]
            return dict(account=a, contact=contact, start=start, status=status, connected=status == "CONNECTED", duration=rnd.randint(40, 900) if status == "CONNECTED" else 0,
                        direction=direction, org=oid, agent=ag, mode=mode, dialer=dialer, sid=new_sid(dialer, start), mirror=None)

        sessions, by_acct = [], defaultdict(list)
        for a in accts:
            nums = [r["contact_no"] for r in ccn[a["customer_id"]]]
            for d in sorted(rnd.sample(range(n_days), rnd.randint(7, 15))):
                day = START + timedelta(days=d)
                s = make_session(a, nums[0] if rnd.random() < 0.8 else nums[-1], local_dt(day, 9, 0) + timedelta(seconds=rnd.randint(0, 8 * 3600 + 1800)))
                sessions.append(s)
                by_acct[a["id"]].append(s)
            if rnd.random() < 0.03:
                s = make_session(a, nums[0], local_dt(START + timedelta(days=rnd.randrange(n_days)), 11, 0), "CONNECTED", "INBOUND")
                sessions.append(s)
                by_acct[a["id"]].append(s)
        # outside the window: the lender's rule in force that day decides
        for a in accts:
            lender = a["institution_code"]
            ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
            if ss and rnd.random() < 0.06:
                s = rnd.choice(ss)
                day, kind = s["start"].date(), rnd.random()
                end_t = pick(WINDOW_END[lender], day)
                if kind < 0.35:
                    s["start"] = local_dt(day, end_t.hour, min(end_t.minute + rnd.randint(1, 9), 59), rnd.randint(0, 59))
                elif kind < 0.7:
                    s["start"] = local_dt(day, rnd.choice([19, 20]), rnd.randint(0, 40))
                else:
                    s["start"] = local_dt(day, rnd.choice([WINDOW_START[lender].hour - 2, WINDOW_START[lender].hour - 1]), rnd.randint(0, 59))
        # bursts to one contact number in a day: cap+1 breaches, exactly the cap is fine
        for a in accts:
            lender = a["institution_code"]
            ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
            r = rnd.random()
            if ss and r < 0.10:
                base = rnd.choice(ss)
                day = base["start"].date()
                cap = pick(DAILY_CAP[lender], day)
                have = sum(1 for s in ss if s["contact"] == base["contact"] and s["start"].date() == day)
                for k in range(max((cap + 1 if r < 0.05 else cap) - have, 0)):
                    s2 = make_session(a, base["contact"], local_dt(day, 10 + (k % 6), rnd.randint(0, 59)), "NO_ANSWER")
                    sessions.append(s2)
                    by_acct[a["id"]].append(s2)
        # calls mirrored in both dialers: counted once
        mirrors = []
        for s in sessions:
            if s["direction"] == "OUTBOUND" and rnd.random() < 0.02:
                other = "COGNIFAI" if s["dialer"] == "SLASHRTC" else "SLASHRTC"
                mirrors.append(dict(s, dialer=other, sid=new_sid(other, s["start"]), mirror=s))
        for a in rnd.sample(accts, max(8, int(80 * scale))):  # a day where a naive count with the mirrors would exceed the cap
            lender = a["institution_code"]
            ss = [s for s in by_acct[a["id"]] if s["direction"] == "OUTBOUND" and s["status"] != "SYSTEM_FAILURE"]
            if not ss:
                continue
            base = ss[0]
            day = base["start"].date()
            have = [s for s in ss if s["contact"] == base["contact"] and s["start"].date() == day]
            for k in range(pick(DAILY_CAP[lender], day) - len(have)):
                s2 = make_session(a, base["contact"], local_dt(day, 10 + k % 6, rnd.randint(0, 59)), "NO_ANSWER")
                sessions.append(s2)
                by_acct[a["id"]].append(s2)
                have.append(s2)
            for s2 in have[:2]:
                other = "COGNIFAI" if s2["dialer"] == "SLASHRTC" else "SLASHRTC"
                mirrors.append(dict(s2, dialer=other, sid=new_sid(other, s2["start"]), mirror=s2))
        sessions.sort(key=lambda s: (s["start"], s["sid"]))

        # certifications keyed by employee code
        emp_valid, cert_id = {}, 0
        for u in all_agents:
            code = u["employee_code"]
            if not code:
                continue
            r = rnd.random()
            if r < 0.08:
                spans = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 120)), date(2025, 12, 1) + timedelta(days=rnd.randint(0, 270)))]
            elif r < 0.12:
                lapse = date(2026, 1, 1) + timedelta(days=rnd.randint(0, 200))
                spans = [(date(2025, 1, 1), lapse), (lapse + timedelta(days=rnd.randint(30, 70)), date(2027, 12, 31))]
            elif r < 0.15:
                spans = []
            else:
                spans = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 200)), date(2027, 6, 30))]
            emp_valid[code] = spans
            for vf, vt in spans:
                cert_id += 1
                add("compliance.collector_certification", cert_id=cert_id, employee_code=code, certification="RECOVERY_AGENT_CERT", certificate_no=f"RAC-{cert_id:06d}", valid_from=vf, valid_to=vt,
                    issuer="Indian Institute of Collections")

        def dts(ts, dialer):
            return ts.astimezone(dialer_tz[dialer]).replace(tzinfo=None)

        tpicl = teia = act = rec = seg = xr = ptp_id = 0
        ptps = []  # promises made on calls: (account, agent, ts)
        rows_all = sorted([(s, None) for s in sessions] + [(m, m["mirror"]) for m in mirrors], key=lambda p: (p[0]["start"], p[0]["sid"]))
        for s, mirror_of in rows_all:
            a, dialer, sid, ag, oid = s["account"], s["dialer"], s["sid"], s["agent"], s["org"]
            y, m = s["start"].year, s["start"].month
            inst = pinst.get((oid, s["mode"], y, m))
            end_ist = s["start"] + timedelta(seconds=s["duration"])
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
                add("cn_core.tele_process_instance_call_logs", id=tpicl, tele_process_instance_id=inst, call_contact_number=s["contact"], user_contact_number=ag["contact_no"],
                    call_direction=s["direction"], call_status=st, call_session_id=sid, call_start_date_time=dts(a0, dialer), call_end_date_time=dts(a1, dialer),
                    call_duration=s["duration"] if st in ("CONNECTED", "DISPOSED") else 0, call_recording_link=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3" if s["connected"] else None,
                    call_user_id=ag["user_id"], dialer_code=dialer)
            act_id = None
            if s["connected"] and mirror_of is None:
                act += 1
                act_id = act
                disp = rnd.choice(["PTP", "PTP", "RTP", "CALLBACK"])
                add("cn_core.activity_log", id=act, customer_id=a["customer_id"], account_id=a["id"], activity_level="A", activity_type_code="CALL", activity_sub_type_code="TELE",
                    activity_code="OUTBOUND_CALL", target_party_type_code="BORROWER", target_party_customer_id=a["customer_id"], target_party_contact_number_category="MOBILE",
                    target_party_other_contact_number=s["contact"], activity_datetime=end_ist.replace(tzinfo=None), target_party_contacted_status="Y", contacted_party_name=a["_cust"]["name"],
                    contacted_party_relation="SELF", contacted_party_contact_number=s["contact"], disposition_group_code="PROMISE" if disp == "PTP" else "CONTACT", disposition_code=disp,
                    next_activity_code="CALL", next_activity_datetime=end_ist.replace(tzinfo=None) + timedelta(days=3), ptp_amount=a["_emi"] if disp == "PTP" else None,
                    ptp_payment_mode="UPI" if disp == "PTP" else None, party_interaction_status="CONNECTED", created_date=end_ist.replace(tzinfo=None), created_by=ag["user_id"],
                    creation_mode="DIALER", activity_done_by=ag["user_id"], source_system_code=dialer, call_start_datetime=s["start"].replace(tzinfo=None),
                    call_end_datetime=end_ist.replace(tzinfo=None), call_recording_url=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3", call_status="CONNECTED")
                if disp == "PTP" and s["direction"] == "OUTBOUND":
                    ptps.append((a, ag, end_ist))
            teia += 1
            add("cn_core.tele_process_instance_activity", id=teia, tele_process_instance_id=inst, account_id=a["id"], customer_id=a["customer_id"], call_session_id=sid, call_log_id=first_log,
                activity_status="DONE" if act_id else "NONE", activity_log_id=act_id, dialer_code=dialer)
            if mirror_of is not None:
                xr += 1
                add("compliance.call_session_xref", xref_id=xr, dialer_code=mirror_of["dialer"], call_session_id=mirror_of["sid"], mirror_dialer_code=dialer, mirror_session_id=sid,
                    relation="MIRROR", canonical_dialer_code=mirror_of["dialer"])
            if not (s["connected"] and mirror_of is None):
                continue
            rr = rnd.random()
            storage = "AVAILABLE" if rr < 0.94 else "NOT_FOUND" if rr < 0.97 else "RETRIEVAL_FAILED"
            rec += 1
            add("compliance.call_recording", recording_id=rec, dialer_code=dialer, call_session_id=sid,
                recording_url=f"https://rec.example.test/{dialer.lower()}/{sid}.mp3" if storage != "NOT_FOUND" else None, duration_sec=s["duration"] if storage == "AVAILABLE" else None,
                storage_status=storage, checked_at=datetime(2026, 11, 18, 6, 0),
                note={"NOT_FOUND": "No object in the recording store for this session", "RETRIEVAL_FAILED": "Recording store returned an error", "AVAILABLE": None}[storage])
            scenario, transcript = "no_transcript", []
            if storage == "AVAILABLE" and s["direction"] == "OUTBOUND" and a["id"] in ta_set:
                lang = a["_cust"]["preferred_language_code"]
                lang = {"mr": "hi", "en": "en"}.get(lang, lang)
                if rnd.random() < 0.15:
                    lang = "hi-en"
                B, x, disclose = BANK[lang], rnd.random(), rnd.random() < 0.8
                dob = f"{a['_cust']['birth_date']:%d-%m-%Y}"
                fm = dict(agency=agency_name[oid], dob=dob, amt=f"{a['_emi']:,}")
                greet, ask, ans, due, prom, bye = (t.format(**fm) for t in B)
                if x < 0.02:
                    scenario = "no_transcript"
                elif not disclose:
                    scenario, transcript = "no_disclosure", [(2.0, "AGENT", greet, "NONE"), (20.0, "BORROWER", prom, "NONE"), (30.0, "AGENT", bye, "NONE")]
                elif x < 0.06:
                    scenario, transcript = "disclosure_first", [(3.0, "AGENT", due, "DUES_DISCLOSURE"), (30.0, "AGENT", ask, "IDENTITY_CHECK_REQUEST"), (45.0, "BORROWER", ans, "IDENTITY_CHECK_PASS")]
                elif x < 0.09:
                    scenario, transcript = "no_verification", [(2.0, "AGENT", greet, "NONE"), (25.0, "AGENT", due, "DUES_DISCLOSURE"), (40.0, "BORROWER", prom, "NONE")]
                elif x < 0.11:
                    scenario, transcript = "failed_then_disclosed", [(10.0, "AGENT", ask, "IDENTITY_CHECK_REQUEST"), (20.0, "BORROWER", "...", "IDENTITY_CHECK_FAIL"), (40.0, "AGENT", due, "DUES_DISCLOSURE")]
                elif x < 0.13:
                    scenario, transcript = "unclear", [(10.0, "AGENT", "[inaudible]", "UNCLEAR"), (35.0, "AGENT", due, "DUES_DISCLOSURE")]
                else:
                    v = round(rnd.uniform(10, 40), 1)
                    scenario, transcript = "ok", [(2.0, "AGENT", greet, "NONE"), (v, "AGENT", ask, "IDENTITY_CHECK_REQUEST"), (round(v + 12, 1), "BORROWER", ans, "IDENTITY_CHECK_PASS"),
                                                  (round(v + 40, 1), "AGENT", due, "DUES_DISCLOSURE"), (round(v + 60, 1), "BORROWER", prom, "NONE"), (round(v + 75, 1), "AGENT", bye, "NONE")]
                for i, (off, who, txt, tag) in enumerate(transcript, 1):
                    seg += 1
                    add("compliance.call_transcript_segment", segment_id=seg, dialer_code=dialer, call_session_id=sid, seq=i, start_offset_sec=off, speaker=who, utterance=txt, tag=tag,
                        language=lang if who == "AGENT" or lang != "hi-en" else "hi-en", asr_confidence=round(rnd.uniform(0.55 if tag == "UNCLEAR" else 0.8, 0.99), 3),
                        end_offset_sec=off + rnd.randint(3, 12))
            s["_storage"], s["_scenario"] = storage, scenario

        # ================================================================ D4 contact history: messages (WhatsApp, SMS, email); consent events
        msgs, mid = [], 0
        for a in accts:
            nums = [r["contact_no"] for r in ccn[a["customer_id"]]]
            lang = a["_cust"]["preferred_language_code"]
            for _ in range(rnd.randint(8, 22)):
                day = START + timedelta(days=rnd.randrange(n_days))
                ts = local_dt(day, 9, 0) + timedelta(seconds=rnd.randint(0, 9 * 3600))
                ch = rnd.choices(["WHATSAPP", "SMS", "EMAIL"], [0.45, 0.35, 0.20])[0]
                cat = rnd.choices(["COLLECTIONS", "SERVICE", "PROMOTIONAL"], [0.85, 0.08, 0.07])[0]
                mid += 1
                recip = nums[0] if rnd.random() < 0.85 else nums[-1]
                msgs.append(dict(id=mid, a=a, ts=ts, ch=ch, cat=cat, tmpl=template_for(ch, cat, lang), recip=recip,
                                 status=rnd.choices(["DELIVERED", "SENT", "READ", "FAILED"], [0.6, 0.2, 0.1, 0.1])[0]))
        msgs.sort(key=lambda m: m["ts"])
        first_msg = {}
        for m in msgs:
            if m["ch"] != "EMAIL":
                first_msg.setdefault((m["recip"], m["ch"]), m)
        consent_events, cid_seq = [], 0
        cust_of_no = {r["contact_no"]: r["customer_id"] for rows in ccn.values() for r in rows}

        def add_consent(cid, no, ch, purpose, status, eff):
            nonlocal cid_seq
            cid_seq += 1
            row = dict(consent_id=cid_seq, customer_id=cid, contact_no=no, channel=ch, purpose=purpose, status=status, effective_at=eff.replace(tzinfo=None), capture_source=rnd.choice(["app", "ivr", "branch", "web"]))
            consent_events.append(row)
            add("compliance.customer_consent", **row)
        for (no, ch), m in first_msg.items():
            cid = cust_of_no[no]
            f = m["ts"].astimezone(UTC)
            r = rnd.random()
            if r < 0.03:
                continue
            if r < 0.09:
                add_consent(cid, no, ch, "COLLECTIONS", "GRANTED", f + (timedelta(hours=rnd.uniform(1, 5)) if rnd.random() < 0.5 else timedelta(days=rnd.uniform(0.5, 6))))
            else:
                add_consent(cid, no, ch, "COLLECTIONS", "GRANTED", f - timedelta(days=rnd.uniform(2, 60)))
                if r < 0.13:
                    add_consent(cid, no, ch, "COLLECTIONS", "REVOKED", f + timedelta(days=rnd.uniform(20, 120)))
            if rnd.random() < 0.3:
                add_consent(cid, no, ch, "PROMOTIONAL", "GRANTED", f - timedelta(days=rnd.uniform(2, 60)))
        for m in msgs:
            a = m["a"]
            add("cn_core.communication_dashboard_t", id=m["id"], account_id=a["id"], account_number=a["account_number"], message_datetime=m["ts"].replace(tzinfo=None), channel=m["ch"],
                rule_name=f"RULE_{m['cat']}", message_status="SENT" if m["status"] != "FAILED" else "FAILED", customer_id=a["customer_id"], customer_name=a["_cust"]["name"],
                message_type=m["cat"], language=a["_cust"]["preferred_language_code"], sms_contact_no=m["recip"] if m["ch"] != "EMAIL" else None,
                sms_final_message=f"Template {m['tmpl']}", status=m["status"], delivery_status=m["status"],
                delivery_datetime=(m["ts"] + timedelta(seconds=20)).replace(tzinfo=None) if m["status"] != "FAILED" else None, template_id=m["tmpl"])

        # ================================================================ D10 consent and DND (borrower level)
        by_cust_events = defaultdict(list)
        for e in consent_events:
            by_cust_events[e["customer_id"]].append(e)
        reg = 0
        for c in cust_rows:
            ev = sorted(by_cust_events.get(c["id"], []), key=lambda e: e["effective_at"])
            dnd = rnd.random() < 0.12
            for ch in ("CALL", "WHATSAPP", "SMS", "EMAIL"):
                reg += 1
                evs = [e for e in ev if e["channel"] == ch and e["purpose"] == "COLLECTIONS"]
                if ch in ("WHATSAPP", "SMS") and evs:
                    last = evs[-1]
                    status = "GRANTED" if last["status"] == "GRANTED" else "REVOKED"
                    ts, out = evs[0]["effective_at"], (last["effective_at"] if status == "REVOKED" else None)
                    src = evs[0]["capture_source"]
                else:
                    status = rnd.choices(["GRANTED", "NOT_GIVEN", "REVOKED"], [0.8, 0.15, 0.05])[0]
                    ts = datetime(2025, 1, 1) + timedelta(days=rnd.randint(0, 600)) if status != "NOT_GIVEN" else None
                    out = ts + timedelta(days=rnd.randint(30, 200)) if status == "REVOKED" else None
                    src = rnd.choice(["app", "ivr", "branch", "web"]) if status != "NOT_GIVEN" else None
                add("compliance.consent_dnd_registry", registry_id=reg, customer_id=c["id"], channel=ch, consent_status=status, consent_ts=ts, opt_out_ts=out,
                    dnd_status="REGISTERED" if dnd else "NOT_REGISTERED", dnd_registered_ts=datetime(2024, 1, 1) + timedelta(days=rnd.randint(0, 900)) if dnd else None, consent_source=src)

        # ================================================================ D6 PTP ledger and D7 payment feed
        pay_id = 0
        pay_sources = ["UPI", "NACH", "PAYMENT_LINK", "AGENCY_CASH"]

        def payment(a, amount, ts, source=None, ref="EMI", status=None):
            nonlocal pay_id
            pay_id += 1
            source = source or rnd.choices(pay_sources, [0.45, 0.25, 0.20, 0.10])[0]
            nm = a["_cust"]["name"]
            payer = nm if rnd.random() < 0.8 else rnd.choice([f"{nm.split()[0][0]}. {nm.split()[1]}", f"{rnd.choice(FIRST)} {nm.split()[1]}", nm.upper()])
            handle = {"UPI": f"{nm[:2].lower()}****@okbank", "NACH": f"XXXX{rnd.randint(1000, 9999)}", "PAYMENT_LINK": f"pl_{rnd.randint(10**7, 10**8 - 1)}",
                      "AGENCY_CASH": f"AGT-{rnd.choice(all_agents)['employee_code'] or 'NA'}"}[source]
            st = status or rnd.choices(["SUCCESS", "FAILED", "PENDING"], [0.92, 0.05, 0.03])[0]
            add("cn_core.payment_feed", txn_id=pay_id, account_id=a["id"], source=source, amount=amount, txn_ts=ts, payer_name=payer, payer_handle_masked=handle,
                reference_text=f"{ref} {a['account_number'][-6:]}", status=st, reversal_flag="Y" if st == "SUCCESS" and rnd.random() < 0.03 else "N")
        for a, ag, ts in ptps:
            ptp_id += 1
            promised = (ts + timedelta(days=rnd.randint(2, 10))).date()
            amt = a["_emi"] if rnd.random() < 0.7 else round(a["_emi"] * rnd.uniform(0.3, 0.8))
            r = rnd.random()
            status, paid = ("kept", amt) if r < 0.40 else ("partial", round(amt * rnd.uniform(0.3, 0.8))) if r < 0.60 else ("broken", 0)
            add("cn_core.ptp_ledger", ptp_id=ptp_id, account_id=a["id"], promised_date=promised, promised_amount=amt, channel="CALL", captured_by=ag["user_id"],
                captured_ts=ts.astimezone(UTC).replace(tzinfo=None), status=status, amount_paid=paid)
            if paid:
                payment(a, paid, datetime.combine(promised, time(rnd.randint(9, 20), rnd.randint(0, 59))) + timedelta(days=rnd.choice([0, 0, 1])), ref="PTP")
        extra = max(int(4 * n_acc) - pay_id, 0)
        for _ in range(extra):
            a = rnd.choice(accts)
            y, m = rnd.choice(MONTHS)
            payment(a, a["_emi"] if rnd.random() < 0.8 else round(a["_emi"] * rnd.uniform(0.4, 0.9)), datetime(y, m, rnd.randint(1, 28), rnd.randint(8, 21), rnd.randint(0, 59)))

        # ================================================================ D8 AA bank statements, D9 bureau snapshots
        aa_n = int(n_borr * 20_000 / 85_000)
        stmt = 0
        for c in rnd.sample(cust_rows, aa_n):
            bal = rnd.uniform(2_000, 40_000)
            salary = rnd.choice([12_000, 18_000, 25_000, 40_000, 65_000])
            emp = rnd.choice(["Zenith Logistics", "Arogya Clinic", "Metro Retail", "Self Employed", "Daily Wage Contractor"])
            for y, m in MONTHS:
                events = [(rnd.randint(1, 5), salary, 0, f"SALARY CREDIT {emp}", emp)]
                events.append((rnd.randint(5, 10), 0, rnd.choice([1500, 3000, 5000]), "NACH DR LOAN EMI", "LOAN"))
                for _ in range(rnd.randint(4, 8)):
                    kind = rnd.choice(["UPI", "ATM", "BILL", "UPI", "FUEL"])
                    amt = rnd.randint(100, 3500)
                    nar = {"UPI": f"UPI/{rnd.randint(10**11, 10**12 - 1)}/{rnd.choice(FIRST)}", "ATM": "ATM WDL", "BILL": "BILLPAY ELECTRICITY", "FUEL": "POS FUEL STATION"}[kind]
                    events.append((rnd.randint(1, 28), 0, amt, nar, kind))
                for day, cr, dr, nar, hint in sorted(events):
                    bal = max(bal + cr - dr, 0)
                    stmt += 1
                    add("cn_core.aa_bank_statement", stmt_id=stmt, customer_id=c["id"], txn_date=date(y, m, day), narration=nar, debit=dr or None, credit=cr or None, balance=round(bal, 2), counterparty_hint=hint)
        snap = trade = 0
        dpd_by_cust = defaultdict(int)
        for a in accts:
            dpd_by_cust[a["customer_id"]] = max(dpd_by_cust[a["customer_id"]], a["dpd"])
        for c in cust_rows:
            base = 760 - dpd_by_cust[c["id"]] * 1.3 + rnd.randint(-40, 40)
            phone = ccn[c["id"]][0]["contact_no"]
            for k, (y, m) in enumerate(MONTHS):
                snap += 1
                add("cn_core.bureau_snapshot", snapshot_id=snap, customer_id=c["id"], snapshot_month=date(y, m, 1), bureau_score=int(max(300, min(900, base - (12 - k) * 2))),
                    enquiries_30d=rnd.choice([0, 0, 1, 2, 4]), enquiries_90d=rnd.choice([0, 1, 3, 5, 8]), utilisation_pct=round(rnd.uniform(20, 98), 2),
                    reported_phone=phone if rnd.random() < 0.7 else f"{rnd.choice('6789')}{rnd.randint(10**8, 10**9 - 1)}", reported_address=f"{c['city']}, {c['state']}")
                if k == len(MONTHS) - 1:
                    for _ in range(rnd.randint(1, 4)):
                        trade += 1
                        dp = "".join(rnd.choice(["000", "000", "030", "060", "090"]) for _ in range(6))
                        add("cn_core.bureau_tradeline", tradeline_id=trade, snapshot_id=snap, lender_type=rnd.choice(["BANK", "NBFC", "MFI", "FINTECH"]), product=rnd.choice(["PL", "TW", "BL", "CC", "JLG"]),
                            sanctioned_amount=rnd.choice([30_000, 80_000, 200_000, 500_000]), outstanding_amount=rnd.randint(5_000, 300_000), dpd_string=dp, opened_date=date(2022, 1, 1) + timedelta(days=rnd.randint(0, 1200)))

        # ================================================================ D13 channel cost and capacity
        ccid = 0
        for ch, cost in [("CALL", 4.5), ("WHATSAPP", 0.9), ("SMS", 0.2), ("EMAIL", 0.05)]:
            for ag in [agency_name[o] for o in TELE] + ["DIGITAL"]:
                if ag == "DIGITAL" and ch == "CALL":
                    continue
                for b in ("0-30", "31-60", "61-90", "90+"):
                    ccid += 1
                    add("cn_core.channel_cost_capacity", id=ccid, channel=ch, agency=ag, bucket=b, cost_per_attempt=round(cost * rnd.uniform(0.85, 1.25), 3), daily_capacity=rnd.choice([2_000, 5_000, 12_000]) if ch != "CALL" else rnd.choice([400, 900, 1_500]),
                        connect_rate=round(rnd.uniform(0.25, 0.65) if ch == "CALL" else rnd.uniform(0.6, 0.97), 3), ptp_rate=round(rnd.uniform(0.04, 0.18), 3), period="2026-H1")

        # ================================================================ notices (trigger, dispatch, served)
        notices, nid, ndoc = [], 0, 0
        for a in accts:
            if rnd.random() >= 0.65:
                continue
            stt = a["_cust"]["state"]
            for _ in range(200):
                trig = date(2025, 11, 4) + timedelta(days=rnd.randint(0, 340))
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
                    disp = served = None
                elif r2 < 0.04:
                    served = None

                def late(x, lim, cal, t=trig):
                    return None if x is None else bdays(t, x, cal) > lim
                if disp is not None and late(disp, NOTICE_DISPATCH_BDAYS, nat) != late(disp, NOTICE_DISPATCH_BDAYS, both):
                    continue
                if served is not None and late(served, NOTICE_SERVE_BDAYS, nat) != late(served, NOTICE_SERVE_BDAYS, both):
                    continue
                if (disp and disp.weekday() >= 5) or (served and served.weekday() >= 5):
                    continue
                nid += 1
                row = dict(notice_id=nid, account_id=a["id"], notice_type=rnd.choice(["DEMAND_NOTICE", "LEGAL_NOTICE"]), trigger_event="DPD_THRESHOLD", trigger_date=trig, dispatch_date=disp,
                           served_date=served, dispatch_mode=rnd.choice(["REGISTERED_POST", "COURIER", "EMAIL"]), borrower_state=stt)
                add("compliance.notice", **row)
                notices.append(row)
                if disp:
                    ndoc += 1
                    add("cn_core.notice_document", id=ndoc, notice_id=nid, document_version_no=1, is_latest_version=1, document_link=f"https://docs.example.test/notice/{nid}.pdf",
                        document_date=datetime.combine(disp, time(10, 0)), notice_reference_no=f"NR-{nid:07d}")
                break

        # ================================================================ oracle: the rules applied to the generated rows
        gaps, cnd = set(), set()
        per_contact_day = defaultdict(list)
        for s in sessions:
            if s["direction"] != "OUTBOUND" or s["status"] == "SYSTEM_FAILURE":
                continue
            aid, d, lender = s["account"]["id"], s["start"].date(), s["account"]["institution_code"]
            if not (WINDOW_START[lender] <= s["start"].timetz().replace(tzinfo=None) < pick(WINDOW_END[lender], d)):
                gaps.add((aid, "Q2"))
            per_contact_day[(aid, s["contact"], d)].append(s)
            code = s["agent"]["employee_code"]
            if code is None:
                cnd.add((aid, "Q6"))
            elif not any(vf <= d <= vt for vf, vt in emp_valid.get(code, [])):
                gaps.add((aid, "Q6"))
        for (aid, _, d), ss in per_contact_day.items():
            if len(ss) > pick(DAILY_CAP[acct_by_id[aid]["institution_code"]], d):
                gaps.add((aid, "Q3"))
        for s in sessions:
            if s["direction"] != "OUTBOUND" or not s["connected"]:
                continue
            aid, stor, scen = s["account"]["id"], s["_storage"], s["_scenario"]
            if stor == "NOT_FOUND":
                gaps.add((aid, "Q7"))
                cnd.add((aid, "Q4"))
            elif stor == "RETRIEVAL_FAILED":
                cnd.add((aid, "Q7"))
                cnd.add((aid, "Q4"))
            elif scen in ("no_transcript", "unclear"):
                cnd.add((aid, "Q4"))
            elif scen in ("disclosure_first", "no_verification", "failed_then_disclosed"):
                gaps.add((aid, "Q4"))
        ev_by_key = defaultdict(list)
        for e in consent_events:
            ev_by_key[(e["contact_no"], e["channel"])].append(e)
        for m in msgs:
            if m["ch"] == "EMAIL" or m["status"] == "FAILED":
                continue
            granted = set()
            for c in sorted((c for c in ev_by_key[(m["recip"], m["ch"])] if c["effective_at"].replace(tzinfo=UTC) < m["ts"].astimezone(UTC)), key=lambda c: c["effective_at"]):
                (granted.add if c["status"] == "GRANTED" else granted.discard)(c["purpose"])
            if not (m["cat"] in granted or (m["cat"] == "SERVICE" and "COLLECTIONS" in granted)):
                gaps.add((m["a"]["id"], "Q1"))
        for n in notices:
            t0 = n["trigger_date"]
            if (n["dispatch_date"] is None or bdays(t0, n["dispatch_date"], nat) > NOTICE_DISPATCH_BDAYS or n["served_date"] is None
                    or bdays(t0, n["served_date"], nat) > NOTICE_SERVE_BDAYS):
                gaps.add((n["account_id"], "Q5"))
        cnd -= gaps

        # ================================================================ sample, request and gap key (the audit samples accounts that have transcripts)
        ta_accts = [a for a in accts if a["id"] in ta_set]
        sample_n = min(300, len(ta_accts))
        sample_accts = rnd.sample(ta_accts, sample_n)
        amb_nums = {x["account_number"] for x, _ in ambiguous}
        refs = [a["account_number"] for a in sample_accts]
        for typo in ("SB00000001", "KF99999999", "GM12"):
            refs.insert(rnd.randrange(len(refs)), typo)
        matched = {a["id"] for a in sample_accts if a["account_number"] not in amb_nums}
        qn = {"Q1": "consent_before_contact", "Q2": "calling_hours", "Q3": "calling_frequency", "Q4": "verification_before_disclosure", "Q5": "notice_timeline", "Q6": "agent_certification",
              "Q7": "recording_completeness"}
        gk = ROOT / "eval" / "gap_keys"
        gk.mkdir(parents=True, exist_ok=True)
        key = sorted((a, q) for a, q in gaps if a in matched)
        for fname, rows, status in (("CN-01.csv", key, "gap"), ("CN-01_cannot_determine.csv", sorted((a, q) for a, q in cnd if a in matched), "cannot_determine")):
            with (gk / fname).open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["account_id", "question_ref", "check_type", "status"])
                w.writerows([[a, q, qn[q], status] for a, q in rows])
        (ROOT / "eval" / "requests").mkdir(parents=True, exist_ok=True)
        (ROOT / "eval" / "requests" / "CN-01.txt").write_text(REQUEST.format(n=len(refs), refs=", ".join(refs)), encoding="utf-8")
        by_q = defaultdict(int)
        for _, q in key:
            by_q[q] += 1

        # ================================================================ load
        order = ["uamdb.organization_type", "uamdb.organization", "uamdb.roles", "uamdb.users", "uamdb.user_role_link", "cn_core.institution", "cn_core.lender", "cn_core.branch",
                 "cn_core.customer", "cn_core.customer_contact_number", "cn_core.customer_email", "cn_core.customer_address", "cn_core.customer_name_variant", "cn_core.account",
                 "cn_core.account_customer_contact_number", "cn_core.account_payment_schedule", "cn_core.collection_case", "cn_core.disposition_group", "cn_core.disposition_code",
                 "cn_core.tele_campaign", "cn_core.tele_process_type", "cn_core.tele_process_instance", "cn_core.tele_process_instance_user_link", "cn_core.tele_process_instance_call_logs",
                 "cn_core.activity_log", "cn_core.tele_process_instance_activity", "cn_core.digital_template", "cn_core.communication_dashboard_t", "cn_core.notice_document",
                 "cn_core.ptp_ledger", "cn_core.payment_feed", "cn_core.aa_bank_statement", "cn_core.bureau_snapshot", "cn_core.bureau_tradeline", "cn_core.channel_cost_capacity",
                 "compliance.dialer_config", "compliance.call_session_xref", "compliance.calling_policy_rule", "compliance.holiday_calendar", "compliance.customer_consent",
                 "compliance.consent_dnd_registry", "compliance.collector_certification", "compliance.call_recording", "compliance.call_transcript_segment", "compliance.notice"]
        print("Replacing the data (previous audit runs referred to the old data and are cleared)...")
        conn.execute("TRUNCATE " + ", ".join(order) + ", audit.runs RESTART IDENTITY CASCADE")
        S.load(order)
        # the same loan number under two lenders
        for x, y in ambiguous:
            conn.execute("UPDATE cn_core.account SET account_number = %s WHERE id = %s", (x["account_number"], y["id"]))
        conn.commit()
        from gen_policy_library import load_policy_library  # noqa: E402  (document seeding lives in its own module)
        n_docs = load_policy_library(conn, rnd)
        conn.commit()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"  policy library (D12): {n_docs} documents in the knowledge base")
    print(f"  request eval/requests/CN-01.txt: {len(refs)} loan references ({sample_n} matched or ambiguous, 3 unmatched)")
    print(f"  gap key eval/gap_keys/CN-01.csv: {len(key)} true gaps in the matched sample: " + ", ".join(f"{q}={n}" for q, n in sorted(by_q.items())))
    print(f"  cannot-determine key: {len([1 for a, q in cnd if a in matched])} (account x question)")


REQUEST = """Subject: Audit request CO-04 - outsourced collections, FY26 sample

From: Internal Audit, Example Lender Group (synthetic request)

Please provide evidence for the {n} sampled loan accounts listed below (by loan account number), covering November 2025 to October 2026.

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
    ap.add_argument("--scale", type=float, default=0.1, help="1.0 = the full proposed volumes (about 6 million rows)")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    main(a.scale, a.seed)
