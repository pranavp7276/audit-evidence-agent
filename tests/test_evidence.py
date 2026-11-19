"""The four checks added with the evidence tags, and the rule that the database holds only what an audit reads."""
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from agent.checks import REGISTRY
from agent.checks import caller_id_registered as cli_mod
from agent.checks import collector_active as agt_mod
from agent.checks import template_approval as tpl_mod
from agent.checks import third_party_disclosure as cnt_mod
from agent.core.contracts import CheckSpec, CheckType, Status

needs_db = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="no DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]


def _run(cls, **patches):
    mods = {"template_approval": tpl_mod, "collector_active": agt_mod, "caller_id_registered": cli_mod, "third_party_disclosure": cnt_mod}
    mod = mods[cls.check_type]
    for name, fn in patches.items():
        setattr(mod, name, fn)
    spec = CheckSpec(check_id="Q", question_ref="Q", question_text="t", check_type=CheckType(cls.check_type), sample={}, test={"severity": "Major"}, sources=[])
    return cls(spec, ["Critical", "Major"]).run(["A1"])


def _call(**kw):
    base = {"session_key": "SLASHRTC:S1", "dialer_code": "SLASHRTC", "started_ts_utc": datetime(2026, 7, 10, 6, 0, tzinfo=UTC), "started_ts_src": "2026-07-10 11:30:00",
            "started_ts_src_tz": "Asia/Kolkata", "employee_code": "EMP1", "collector_user_id": 5, "agency_code": "NSTAR", "cli_number": "9000000001", "contact_type": "PRIMARY",
            "contact_source": "LOS", "connected": True, "process_mode": "MANUAL", "source_system": "contact_log", "source_table": "t", "record_key": "SLASHRTC:S1",
            "record_ts_utc": None, "record_ts_original": None}
    return {**base, **kw}


def _row(table, key, **kw):
    return {"source_system": "collector_roster", "source_table": table, "record_key": key, "record_ts_utc": None, "record_ts_original": None, **kw}


# ---------------------------------------------------------------- TPL-01


def _msg(sent):
    return {"message_id": "7", "channel": "WHATSAPP", "contact_no": "9876543210", "status": "DELIVERED", "template_id": 11, "sent_ts_utc": sent, "sent_ts_src": "x", "sent_ts_src_tz": "Asia/Kolkata",
            "source_system": "contact_log", "source_table": "m", "record_key": "7", "record_ts_utc": sent, "record_ts_original": "x"}


def _tpl(status="APPROVED", approved=datetime(2026, 1, 1), retired=None):
    return _row("cn_core.digital_template", "11", template_id="11", sms_category="COLLECTIONS", digital_channel="WHATSAPP", approval_status=status, approved_at=approved, retired_at=retired)


@pytest.mark.parametrize("tpl,sent,status,words", [
    (_tpl(), datetime(2026, 6, 1, tzinfo=UTC), Status.EVIDENCED, "approved 2026-01-01"),
    (_tpl(approved=datetime(2026, 8, 1)), datetime(2026, 6, 1, tzinfo=UTC), Status.GAP, "before the template was approved"),
    (_tpl(status="EXPIRED", retired=datetime(2026, 3, 1)), datetime(2026, 6, 1, tzinfo=UTC), Status.GAP, "expired in the registry"),
    (_tpl(status="PENDING", approved=None), datetime(2026, 6, 1, tzinfo=UTC), Status.GAP, "pending in the registry"),
    (_tpl(retired=datetime(2026, 5, 1)), datetime(2026, 6, 1, tzinfo=UTC), Status.GAP, "after the template was retired"),
    (_tpl(retired=datetime(2026, 7, 1)), datetime(2026, 6, 1, tzinfo=UTC), Status.EVIDENCED, "approved"),   # retired later than the send: fine
    (None, datetime(2026, 6, 1, tzinfo=UTC), Status.GAP, "no template on record"),
])
def test_template_approval_judges_the_template_at_the_time_of_sending(tpl, sent, status, words):
    f = _run(REGISTRY[CheckType.TEMPLATE_APPROVAL], get_messages=lambda *a, **k: [_msg(sent)], get_template=lambda *a, **k: tpl)[0]
    assert f.status is status and words in f.reason and f.citations


# ---------------------------------------------------------------- AGT-01


def _status(st, frm, to=None):
    return _row("compliance.collector_status", "1", employee_code="EMP1", status=st, valid_from=frm, valid_to=to)


@pytest.mark.parametrize("history,status,words", [
    ([_status("ACTIVE", date(2025, 1, 1))], Status.EVIDENCED, "was active"),
    ([_status("ACTIVE", date(2025, 1, 1), date(2026, 3, 23)), _status("TERMINATED", date(2026, 3, 24))], Status.GAP, "terminated since 2026-03-24"),
    ([_status("ACTIVE", date(2025, 1, 1), date(2026, 6, 1)), _status("INACTIVE", date(2026, 6, 2), date(2026, 7, 31)), _status("ACTIVE", date(2026, 8, 1))], Status.GAP, "inactive from"),
    ([], Status.CANNOT_DETERMINE, "no status history"),
])
def test_collector_status_is_read_on_the_ist_date_of_the_call(history, status, words):
    f = _run(REGISTRY[CheckType.COLLECTOR_ACTIVE], get_calls=lambda *a, **k: [_call()], get_collector_status=lambda code: history)[0]
    assert f.status is status and words in f.reason


def test_a_collector_without_an_employee_code_cannot_be_looked_up():
    f = _run(REGISTRY[CheckType.COLLECTOR_ACTIVE], get_calls=lambda *a, **k: [_call(employee_code=None)], get_collector_status=lambda code: [])[0]
    assert f.status is Status.CANNOT_DETERMINE


# ---------------------------------------------------------------- CLI-01


def _reg(frm, to=None):
    return _row("compliance.registered_cli", "9", cli_id="9", cli_number="9000000001", agency_code="NSTAR", purpose="COLLECTIONS", valid_from=frm, valid_to=to)


@pytest.mark.parametrize("regs,status,words", [
    ([_reg(date(2025, 1, 1))], Status.EVIDENCED, "registered to NSTAR"),
    ([], Status.GAP, "not on NSTAR's registered caller ID list"),
    ([_reg(date(2026, 9, 1))], Status.GAP, "only from 2026-09-01"),
    ([_reg(date(2025, 1, 1), date(2026, 6, 30))], Status.GAP, "ended on 2026-06-30"),   # registration ended before the call
])
def test_the_caller_number_must_be_registered_to_the_agency_on_the_day(regs, status, words):
    f = _run(REGISTRY[CheckType.CALLER_ID_REGISTERED], get_calls=lambda *a, **k: [_call()], get_registered_clis=lambda agency, cli: regs)[0]
    assert f.status is status and words in f.reason
    assert "9000000001" not in f.reason, "the number is masked in the reason"


# ---------------------------------------------------------------- CNT-01


def _seg(tag, off=20.0):
    return _row("compliance.call_transcript_segment", "3", seq=1, start_offset_sec=off, speaker="AGENT", tag=tag)


@pytest.mark.parametrize("ctype,rec,segs,status,words", [
    ("PRIMARY", None, [], Status.EVIDENCED, "provided"),
    ("REFERENCE", "AVAILABLE", [_seg("DUES_DISCLOSURE", 25.0)], Status.GAP, "disclosed dues at 25s"),
    ("REFERENCE", "AVAILABLE", [_seg("NONE")], Status.EVIDENCED, "no disclosure of dues"),
    ("REFERENCE", "NOT_FOUND", [], Status.CANNOT_DETERMINE, "recording is not available"),
    ("REFERENCE", "AVAILABLE", [], Status.CANNOT_DETERMINE, "no transcript"),
])
def test_dues_must_not_be_disclosed_to_a_reference_contact(ctype, rec, segs, status, words):
    recs = {"SLASHRTC:S1": _row("compliance.call_recording", "r", storage_status=rec, note=None, checked_ts_src="x")} if rec else {}
    f = _run(REGISTRY[CheckType.THIRD_PARTY_DISCLOSURE], get_calls=lambda *a, **k: [_call(contact_type=ctype)], get_recordings=lambda keys: recs,
             get_transcripts=lambda keys: {"SLASHRTC:S1": segs})[0]
    assert f.status is status and words in f.reason


# ---------------------------------------------------------------- the catalog and the database


def test_every_implemented_check_is_in_the_source_map_and_declares_its_tools():
    import yaml
    smap = yaml.safe_load((ROOT / "config" / "source_map.yaml").read_text(encoding="utf-8"))
    mapped = {v for v in smap["checks"].values() if v}
    assert {t.value for t in REGISTRY} == mapped, "a check in agent/checks must be listed under checks: in config/source_map.yaml, and the reverse"
    for cls in REGISTRY.values():
        assert cls.tools and cls.__doc__, f"{cls.__name__} must declare its tools and say what it tests"


@needs_db
def test_every_evidence_tag_is_mapped_and_every_mapped_column_exists():
    from agent.services.evidence_coverage import coverage
    cov = coverage()
    assert cov["problems"] == [], cov["problems"]
    assert cov["counts"]["present"] + cov["counts"]["derived"] > 50


@needs_db
def test_the_database_holds_only_what_an_audit_reads():
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_prune_migration import KEEP
    from retired import RETIRED_COLUMNS, RETIRED_TABLES

    from agent.core.db import read_rows
    have = {r["t"] for r in read_rows("SELECT table_schema || '.' || table_name AS t FROM information_schema.tables WHERE table_schema IN ('cn_core', 'compliance', 'uamdb', 'raw', 'book')")}
    assert not (set(RETIRED_TABLES) & have), "a retired table is back"
    assert not {t for t in have if t.startswith("raw.")}, "the loose-file schema is back"
    assert not {t for t in have if t.split(".")[1] in ("d3_repayment_history", "d6_ptp_ledger", "d7_payment_feed", "d8_bank_statements", "d9_bureau_snapshot", "d13_channel_cost")}
    added = {"compliance.dialer_config": {"clock_source"}, "cn_core.digital_template": {"approved_at", "retired_at"}}  # V018
    for table, keep in KEEP.items():
        if keep is None:
            continue
        schema, name = table.split(".")
        cols = {r["column_name"] for r in read_rows("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s", (schema, name))}
        assert cols == keep | added.get(table, set()), f"{table}: {sorted(cols ^ (keep | added.get(table, set())))}"
        assert not (cols & set(RETIRED_COLUMNS.get(table, ()))), f"{table}: a retired column is back"


@needs_db
def test_no_check_fails_to_run_on_real_data():
    """A check that cites a column that no longer exists fails for the account and reports cannot determine (that is how a removed column once hid 13 gaps)."""
    from agent.core.db import read_rows
    accts = [r["account_id"] for r in read_rows("SELECT account_id FROM staging.accounts ORDER BY md5(account_id) LIMIT 25")]
    for ct, cls in REGISTRY.items():
        spec = CheckSpec(check_id="Q", question_ref="Q", question_text="t", check_type=ct, sample={}, test={"severity": "Major"}, sources=[])
        failed = [f.reason for f in cls(spec, ["Critical", "Major", "Minor"]).run(accts) if f.reason.startswith("Check failed to run")]
        assert not failed, f"{ct.value}: {failed[0]}"


# ---------------------------------------------------------------- the six-month retention window


def test_the_horizon_is_six_calendar_months_back():
    from agent.core.retention import horizon
    assert horizon(date(2026, 11, 20)) == date(2026, 5, 20)
    assert horizon(date(2026, 8, 31)) == date(2026, 2, 28)       # a shorter month
    assert horizon(date(2026, 3, 15)) == date(2025, 9, 15)       # across a year end
    assert horizon(date(2024, 8, 31)) == date(2024, 2, 29)       # a leap year


def test_a_period_before_the_horizon_is_flagged_and_one_inside_it_is_not():
    from agent.core.retention import period_note
    today = date(2026, 11, 20)
    inside = {"start": "2026-06-01", "end": "2026-11-01", "label": "x"}
    reaching_back = {"start": "2025-11-01", "end": "2026-11-01", "label": "x"}
    assert period_note(inside, today) is None and period_note(None, today) is None
    note = period_note(reaching_back, today)
    assert note and "20 May 2026" in note and "cannot determine" in note


def test_the_planner_says_so_when_the_period_reaches_past_the_window():
    from agent.core.retention import horizon
    from agent.core.trace import Trace
    from agent.runtime.planner import build_plan
    old = {"start": (horizon().replace(year=horizon().year - 1)).isoformat(), "end": date.today().isoformat(), "label": "last year"}
    trace = Trace()
    build_plan([], 10, old, "random sample", 0, trace)
    assert any(s["detail"].get("retention") for s in trace.steps)


@needs_db
def test_a_retention_dry_run_counts_and_changes_nothing():
    from agent.core.db import read_rows
    from agent.services.retention import purge
    before = read_rows("SELECT (SELECT count(*) FROM cn_core.tele_process_instance_call_logs) AS calls, (SELECT count(*) FROM cn_core.communication_dashboard_t) AS msgs")[0]
    out = purge(date.today())
    after = read_rows("SELECT (SELECT count(*) FROM cn_core.tele_process_instance_call_logs) AS calls, (SELECT count(*) FROM cn_core.communication_dashboard_t) AS msgs")[0]
    assert before == after and out["applied"] is False and set(out["removed"]) >= {"calls", "messages", "notices"}
    # consent events, certificates and the rules are standing records: no step touches them
    assert not any(k in out["removed"] for k in ("consents", "certificates", "policy rules"))
