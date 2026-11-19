"""The parts of the story that are lookup: the citation read-back, the answer-key match, the trap catalogue."""
from agent.runtime.cite_check import verify_citations
from agent.services import scoring
from agent.services.traps import TRAPS
from agent.tools import record_keys

# ---------------------------------------------------------------- citations read back from the warehouse


def test_every_cited_record_is_looked_up_and_missing_ones_are_reported(monkeypatch):
    def fake_sql(query, params=None, max_rows=0):
        keys = params["keys"]
        return {"rows": [{"k": k} for k in keys if k != "gone"], "truncated": False}

    monkeypatch.setattr(record_keys, "run_sql", fake_sql)
    found, missing = record_keys.verify_records({("compliance.notice", "a"), ("compliance.notice", "gone"), ("cn_core.digital_template", "7"), ("made.up", "x")})
    assert found == 2
    assert {m["record_key"] for m in missing} == {"gone", "x"}
    assert {m["why"] for m in missing} == {"not found in the source table", "unknown source table"}


def test_a_citation_that_does_not_resolve_is_never_hidden(monkeypatch):
    from agent.core.contracts import Citation, Finding, SourceSystem, Status
    from agent.core.trace import Trace

    monkeypatch.setattr("agent.runtime.cite_check.verify_records", lambda refs: (len(refs) - 1, [{"source_table": "t", "record_key": "k", "why": "not found in the source table"}]))
    cite = Citation(source_system=SourceSystem.D4, source_table="compliance.notice", record_key="1")
    f = Finding(check_id="Q1", account_id="A", status=Status.GAP, severity="High", reason="Notice was late by two days.", citations=[cite])
    trace = Trace()
    out = verify_citations(trace, {"Q1": [f, f]})
    assert out["checked"] == 1 and out["verified"] == 0 and len(out["missing"]) == 1
    assert trace.steps[-1]["status"] == "failed" and "1 not found" in trace.steps[-1]["action"]


def test_every_table_a_check_cites_can_be_opened_and_verified():
    cited = {"cn_core.tele_process_instance_call_logs", "cn_core.communication_dashboard_t", "cn_core.digital_template", "compliance.customer_consent",
             "compliance.call_recording", "compliance.call_transcript_segment", "compliance.calling_policy_rule", "compliance.holiday_calendar",
             "compliance.notice", "compliance.collector_certification", "uamdb.users"}
    assert cited <= set(record_keys.KEY_EXPR)


# ---------------------------------------------------------------- answer keys and traps


def test_the_answer_key_is_found_by_the_name_of_the_request():
    assert scoring.find_key("CN-01") and scoring.find_key("cn-01-rerun-2") == scoring.find_key("CN-01")
    assert scoring.find_key("NOPE-9") is None
    assert "cannot_determine" not in scoring.find_key("CN-01").stem


def test_every_trap_names_the_words_the_checks_actually_write():
    """The catalogue counts findings by their wording; if a check's wording changes, this fails instead of the count silently going to zero."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "agent" / "checks"
    source = {p.stem: p.read_text(encoding="utf-8") for p in root.glob("*.py")}
    where = {"consent_before_contact": "consent_before_contact", "calling_hours": "calling_hours_frequency", "recording_completeness": "recording_completeness",
             "agent_certification": "agent_certification", "verification_before_disclosure": "verification_before_disclosure", "notice_timeline": "notice_timeline"}
    for key, check_type, _status, text, _label, _why in TRAPS:
        files = [source[where[check_type]]] if check_type else list(source.values())
        needles = ["(logged", "'outside'", "the permitted"] if key == "timezone" else [text]  # the hours reason is built from pieces
        assert any(all(n in f for n in needles) for f in files), f"trap {key}: no check writes {text!r}"
