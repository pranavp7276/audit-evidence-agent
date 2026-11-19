"""Generate a synthetic, seeded dataset for the audit evidence agent.

Writes the nine source files listed in data/manifest.yaml to data/raw/, a sample audit request to
eval/requests/SYN-01.txt, and the ground-truth gap key to eval/gap_keys/SYN-01.csv.

The data is NOT the organisers' data. Column layouts for D5/D10/D11 are our assumptions
(docs/data_dictionary.md, docs/decisions.md D-008..D-010). Violations are seeded at random and the
gap key is computed by an independent oracle that applies the rules to the final files.

Sources use different time zones on purpose:
  D4 contact log, D10 recordings, notice dates   Asia/Kolkata (naive local strings)
  D5 consent, D11 verification                   UTC (explicit offset)

  python scripts/gen_synthetic_data.py [--seed 42]
"""
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc

N_ACCOUNTS = 2000
N_COLLECTORS = 1200
SAMPLE_SIZE = 300
STATES = ["MH", "KA", "TN", "DL", "GJ", "KL", "UP", "WB", "RJ", "TS"]

HOURS_START, HOURS_END = time(8, 0), time(19, 0)  # D12: [start, end) borrower local time
MAX_CALLS_PER_DAY = 3
NOTICE_SLA_BDAYS = 5

NATIONAL_HOLIDAYS = {
    date(2026, 1, 26): "Republic Day", date(2026, 3, 4): "Holi", date(2026, 4, 3): "Good Friday",
    date(2026, 8, 15): "Independence Day", date(2026, 10, 2): "Gandhi Jayanti",
    date(2026, 11, 8): "Diwali", date(2026, 12, 25): "Christmas",
    date(2027, 1, 26): "Republic Day", date(2027, 3, 22): "Holi", date(2027, 8, 15): "Independence Day",
    date(2027, 10, 2): "Gandhi Jayanti", date(2027, 12, 25): "Christmas",
}
STATE_HOLIDAYS = [
    (date(2026, 1, 15), "Pongal", "TN"), (date(2026, 5, 1), "Maharashtra Day", "MH"),
    (date(2026, 5, 1), "Gujarat Day", "GJ"), (date(2026, 8, 26), "Onam", "KL"),
    (date(2026, 11, 1), "Karnataka Rajyotsava", "KA"), (date(2026, 2, 19), "Shivaji Jayanti", "MH"),
    (date(2026, 9, 14), "Ganesh Chaturthi", "MH"), (date(2027, 1, 15), "Pongal", "TN"),
]


def write_csv(name: str, header: list[str], rows: list[list]) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote data/raw/{name:<26} {len(rows):>7,} rows")


def ist_str(dt: datetime) -> str:
    return dt.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S")


def utc_str(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def bdays_between(start: date, end: date, holidays: set[date]) -> int:
    """Business days in (start, end]: Mon-Fri, not a holiday."""
    n, d = 0, start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            n += 1
    return n


def add_bdays(start: date, n: int, holidays: set[date]) -> date:
    d = start
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            n -= 1
    return d


def main(seed: int) -> None:
    rnd = random.Random(seed)
    print(f"Generating synthetic data (seed {seed})")

    # --- collectors and certificates -------------------------------------------------------
    collectors = [f"COL{i:04d}" for i in range(1, N_COLLECTORS + 1)]
    roster = [[c, f"Collector {i}", rnd.choice(["Apex Recoveries", "Northstar BPO", "Meridian Collect", "Sunrise Agency"]),
               rnd.choice(STATES), "active"] for i, c in enumerate(collectors, 1)]
    cert_plan: dict[str, list[tuple[date, date]]] = {}
    for c in collectors:
        r = rnd.random()
        if r < 0.06:  # expires mid-2026
            cert_plan[c] = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 120)),
                             date(2026, 3, 1) + timedelta(days=rnd.randint(0, 180)))]
        elif r < 0.09:  # lapsed, then renewed
            lapse = date(2026, 3, 1) + timedelta(days=rnd.randint(0, 120))
            cert_plan[c] = [(date(2025, 1, 1), lapse), (lapse + timedelta(days=rnd.randint(30, 70)), date(2027, 12, 31))]
        else:
            cert_plan[c] = [(date(2025, 1, 1) + timedelta(days=rnd.randint(0, 200)), date(2027, 6, 30))]

    # --- accounts and contacts (D4) ---------------------------------------------------------
    accounts = [f"ACC{i:05d}" for i in range(1, N_ACCOUNTS + 1)]
    acct_state = {a: rnd.choice(STATES) for a in accounts}
    primary = {a: rnd.choice(collectors) for a in accounts}
    start_day, end_day = date(2026, 1, 5), date(2026, 10, 30)
    span = (end_day - start_day).days

    contacts: list[dict] = []  # contact_id, account_id, collector_id, channel, outcome, disclosed, ts (aware IST)

    def add_contact(a: str, ts: datetime, channel: str, collector: str | None = None) -> dict:
        connected = channel == "call" and rnd.random() < 0.55
        row = {
            "account_id": a, "collector_id": collector or (primary[a] if rnd.random() < 0.9 else rnd.choice(collectors)),
            "channel": channel, "ts": ts,
            "outcome": ("connected" if connected else "no_answer") if channel == "call" else "delivered",
            "disclosed": "Y" if connected and rnd.random() < 0.8 else "N",
            "template_id": f"T{rnd.randint(1, 8):02d}" if channel != "call" else None,
        }
        contacts.append(row)
        return row

    for a in accounts:
        days = sorted(rnd.sample(range(span), rnd.randint(6, 10)))
        for d in days:
            ch = rnd.choices(["call", "whatsapp", "sms"], [0.6, 0.3, 0.1])[0]
            day9 = datetime.combine(start_day + timedelta(days=d), time(9, 0), tzinfo=IST)
            ts = day9 + timedelta(seconds=rnd.randint(0, 9 * 3600))
            add_contact(a, ts, ch)

    # Seed violations
    calls_by_acct: dict[str, list[dict]] = defaultdict(list)
    for c in contacts:
        if c["channel"] == "call":
            calls_by_acct[c["account_id"]].append(c)
    for a in accounts:
        calls = calls_by_acct.get(a, [])
        if not calls:
            continue
        if rnd.random() < 0.05:  # outside permitted hours
            c = rnd.choice(calls)
            hour = rnd.choice([6, 7, 19, 20, 21])
            minute = rnd.randint(15, 59) if hour == 19 else rnd.randint(0, 59)
            c["ts"] = c["ts"].replace(hour=hour, minute=minute, second=rnd.randint(0, 59))
        if rnd.random() < 0.04:  # too many attempts in one day
            base = rnd.choice(calls)["ts"]
            for k in range(3):
                add_contact(a, base.replace(hour=10 + k * 2, minute=rnd.randint(0, 59)), "call")

    contacts.sort(key=lambda c: (c["ts"], c["account_id"]))
    for i, c in enumerate(contacts, 1):
        c["contact_id"] = f"CT{i:07d}"

    # --- consent (D5, UTC) -------------------------------------------------------------------
    consents, first_msg = [], {}
    for c in contacts:
        if c["channel"] in ("whatsapp", "sms"):
            first_msg.setdefault((c["account_id"], c["channel"]), c["ts"])
    for (a, ch), first in sorted(first_msg.items()):
        r = rnd.random()
        if r < 0.03:
            continue  # no consent record at all
        if r < 0.11:  # captured after the first message, often by hours only (time-zone trap)
            ts = first + (timedelta(hours=rnd.uniform(1, 5)) if rnd.random() < 0.5 else timedelta(days=rnd.uniform(0.5, 6)))
        else:
            ts = first - timedelta(days=rnd.uniform(2, 60))
        source = rnd.choice(["app", "ivr", "branch", "web"])
        consents.append([f"CN{len(consents) + 1:06d}", a, ch, utc_str(ts), "granted", source])

    # --- recordings (D10, IST) and verification (D11, UTC) ----------------------------------
    recordings, verifications = [], []
    for c in contacts:
        if c["channel"] != "call" or c["outcome"] != "connected":
            continue
        if rnd.random() >= 0.03:
            rid = f"REC{len(recordings) + 1:06d}"
            c["recording_id"] = rid
            recordings.append([rid, c["contact_id"], c["account_id"], ist_str(c["ts"] + timedelta(seconds=2)),
                               rnd.randint(40, 900), f"s3://recordings/{rid}.mp3"])
        if c["disclosed"] == "Y":
            r = rnd.random()
            if r < 0.04:
                continue  # no verification on file
            if r < 0.09:
                vts, result = c["ts"] + timedelta(minutes=rnd.uniform(2, 10)), "passed"  # after disclosure
            elif r < 0.11:
                vts, result = c["ts"] - timedelta(seconds=rnd.randint(30, 150)), "failed"  # disclosed despite fail
            else:
                vts, result = c["ts"] - timedelta(seconds=rnd.randint(30, 150)), "passed"
            verifications.append([f"VF{len(verifications) + 1:06d}", c["account_id"], c["contact_id"], utc_str(vts),
                                  rnd.choice(["dob", "pan_last4", "otp"]), result])

    # Nudge certificate boundaries off any call date so "inclusive expiry" is never in play
    call_dates: dict[str, set[date]] = defaultdict(set)
    for c in contacts:
        if c["channel"] == "call":
            call_dates[c["collector_id"]].add(c["ts"].date())
    certs = []
    for col, spans in cert_plan.items():
        for vf, vt in spans:
            while vf in call_dates[col]:
                vf += timedelta(days=1)
            while vt in call_dates[col]:
                vt += timedelta(days=1)
            certs.append([f"CERT{len(certs) + 1:05d}", col, "Collections Agent Certification", vf.isoformat(), vt.isoformat()])

    # --- notices ---------------------------------------------------------------------------
    state_hol = defaultdict(set)
    for d, _, st in STATE_HOLIDAYS:
        state_hol[st].add(d)
    nat = set(NATIONAL_HOLIDAYS)
    notices = []
    for a in accounts:
        if rnd.random() >= 0.7:
            continue
        for _ in range(100):
            trig = date(2026, 1, 2) + timedelta(days=rnd.randint(0, 300))
            if trig.weekday() >= 5 or trig in nat:
                continue
            late = rnd.random() < 0.10
            n = rnd.randint(7, 12) if late else rnd.randint(1, 4)
            svc = add_bdays(trig, n, nat)
            if svc.weekday() >= 5:
                continue
            both = nat | state_hol[acct_state[a]]
            if (bdays_between(trig, svc, nat) > NOTICE_SLA_BDAYS) != (bdays_between(trig, svc, both) > NOTICE_SLA_BDAYS):
                continue  # state-holiday ambiguity (open question): keep it out of the dataset
            disp = trig + timedelta(days=rnd.randint(0, 2))
            if bdays_between(disp, svc, nat) < 0 or disp > svc:
                disp = trig
            notices.append([f"NT{len(notices) + 1:06d}", a, rnd.choice(["demand_notice", "legal_notice"]), acct_state[a],
                            trig.isoformat(), disp.isoformat(), svc.isoformat()])
            break

    # --- write files ------------------------------------------------------------------------
    write_csv("collector_roster.csv", ["collector_id", "collector_name", "agency", "state", "status"], roster)
    write_csv("cert_register.csv", ["cert_id", "collector_id", "cert_name", "valid_from", "valid_to"], certs)
    holidays = [[d.isoformat(), n, "national", ""] for d, n in sorted(NATIONAL_HOLIDAYS.items())]
    holidays += [[d.isoformat(), n, "state", st] for d, n, st in sorted(STATE_HOLIDAYS)]
    write_csv("holiday_calendar.csv", ["holiday_date", "holiday_name", "scope", "state"], holidays)
    write_csv("D12.csv", ["policy_key", "policy_value", "unit", "applies_to", "note"], [
        ["calling_hours_start", HOURS_START.strftime("%H:%M"), "local_time", "call", "Borrower local time; inclusive"],
        ["calling_hours_end", HOURS_END.strftime("%H:%M"), "local_time", "call", "Borrower local time; exclusive"],
        ["max_calls_per_day", str(MAX_CALLS_PER_DAY), "attempts", "call", "Per account per calendar day (IST)"],
        ["notice_sla_business_days", str(NOTICE_SLA_BDAYS), "business_days", "notice",
         "Trigger date to service date; Mon-Fri excluding national holidays"],
    ])
    write_csv("D4.csv", ["contact_id", "account_id", "collector_id", "channel", "contact_ts", "outcome", "dues_disclosed",
                         "template_id", "recording_id"],
              [[c["contact_id"], c["account_id"], c["collector_id"], c["channel"], ist_str(c["ts"]), c["outcome"],
                c["disclosed"], c["template_id"] or "", c.get("recording_id", "")] for c in contacts])
    write_csv("D5.csv", ["consent_id", "account_id", "channel", "consent_ts", "status", "capture_source"], consents)
    write_csv("D10.csv", ["recording_id", "contact_id", "account_id", "recorded_ts", "duration_sec", "storage_uri"], recordings)
    write_csv("D11.csv", ["verification_id", "account_id", "contact_id", "verified_ts", "method", "result"], verifications)
    write_csv("notice_dispatch.csv", ["notice_id", "account_id", "notice_type", "borrower_state", "trigger_date",
                                      "dispatch_date", "service_date"], notices)

    # --- oracle: apply the rules to the final data -------------------------------------------
    gaps: set[tuple[str, str]] = set()
    cert_spans = defaultdict(list)
    for _, col, _, vf, vt in certs:
        cert_spans[col].append((date.fromisoformat(vf), date.fromisoformat(vt)))
    consent_ts = defaultdict(list)
    for _, a, ch, ts, *_ in consents:
        consent_ts[(a, ch)].append(datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC))
    ver = defaultdict(list)
    for _, _, cid, ts, _, result in verifications:
        ver[cid].append((datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC), result))
    per_day = defaultdict(int)
    for c in contacts:
        a, ts = c["account_id"], c["ts"]
        if c["channel"] in ("whatsapp", "sms"):
            if not any(t < ts for t in consent_ts[(a, c["channel"])]):
                gaps.add((a, "Q1"))
        else:
            per_day[(a, ts.date())] += 1
            if not (HOURS_START <= ts.timetz().replace(tzinfo=None) < HOURS_END):
                gaps.add((a, "Q2"))
            if c["outcome"] == "connected":
                if c["disclosed"] == "Y" and not any(t <= ts and r == "passed" for t, r in ver[c["contact_id"]]):
                    gaps.add((a, "Q4"))
                if "recording_id" not in c:
                    gaps.add((a, "Q7"))
            if not any(vf <= ts.date() <= vt for vf, vt in cert_spans[c["collector_id"]]):
                gaps.add((a, "Q6"))
    gaps |= {(a, "Q3") for (a, _), n in per_day.items() if n > MAX_CALLS_PER_DAY}
    for _, a, _, _, trig, _, svc in notices:
        if bdays_between(date.fromisoformat(trig), date.fromisoformat(svc), nat) > NOTICE_SLA_BDAYS:
            gaps.add((a, "Q5"))

    sample = sorted(rnd.sample(accounts, SAMPLE_SIZE))
    sset = set(sample)
    key_rows = sorted((a, q) for a, q in gaps if a in sset)
    names = {"Q1": "consent_before_contact", "Q2": "calling_hours", "Q3": "calling_frequency",
             "Q4": "verification_before_disclosure", "Q5": "notice_timeline", "Q6": "agent_certification",
             "Q7": "recording_completeness"}
    gk = ROOT / "eval" / "gap_keys"
    gk.mkdir(parents=True, exist_ok=True)
    with (gk / "SYN-01.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["account_id", "question_ref", "check_type", "status"])
        w.writerows([[a, q, names[q], "gap"] for a, q in key_rows])
    req = ROOT / "eval" / "requests"
    req.mkdir(parents=True, exist_ok=True)
    (req / "SYN-01.txt").write_text(REQUEST.format(n=SAMPLE_SIZE, accounts=", ".join(sample)), encoding="utf-8")
    by_q = defaultdict(int)
    for _, q in key_rows:
        by_q[q] += 1
    print(f"  wrote eval/requests/SYN-01.txt ({SAMPLE_SIZE} sampled accounts)")
    print(f"  wrote eval/gap_keys/SYN-01.csv ({len(key_rows)} true gaps in sample: "
          + ", ".join(f"{q}={n}" for q, n in sorted(by_q.items())) + ")")


REQUEST = """Subject: Audit request CO-04 - outsourced collections, FY26 sample

From: Internal Audit, Example Lender Ltd (synthetic request)

Please provide evidence for the {n} sampled accounts listed below, covering January to October 2026.

Q1. For every WhatsApp or SMS message sent, show that the borrower had given consent before it was sent.
Q2. Confirm that every collection call was made within the permitted calling hours.
Q3. Confirm that no borrower was called more often than the permitted daily frequency.
Q4. Where dues were disclosed on a call, show the borrower's identity was verified before disclosure.
Q5. Show that notices were served within the permitted timeline from the trigger date.
Q6. Confirm the recovery agent was certified on the date of each call they made.
Q7. Provide the recording for every connected call.

Severity scale for gaps:
  Critical - regulatory breach affecting the borrower directly (Q1, Q2, Q3, Q4)
  Major    - process breach with documentary impact (Q5, Q6)
  Minor    - evidence completeness (Q7)

Sampled accounts:
{accounts}
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    main(ap.parse_args().seed)
