import pytest
from pydantic import ValidationError

from agent.core.contracts import Citation, Finding, SourceSystem, Status

CITE = Citation(source_system=SourceSystem.D4, source_table="raw.d4_contact_log", record_key="42")


def test_evidenced_without_citation_is_rejected():
    with pytest.raises(ValidationError, match="No claim without a cited record"):
        Finding(check_id="Q1", account_id="A1", status=Status.EVIDENCED, reason="Consent before message.")


def test_gap_without_citation_is_rejected():
    with pytest.raises(ValidationError):
        Finding(check_id="Q1", account_id="A1", status=Status.GAP, severity="High",
                reason="Consent after message.")


def test_gap_without_severity_is_rejected():
    with pytest.raises(ValidationError, match="severity"):
        Finding(check_id="Q1", account_id="A1", status=Status.GAP, reason="Consent after message.",
                citations=[CITE])


def test_cannot_determine_needs_no_citation():
    f = Finding(check_id="Q1", account_id="A1", status=Status.CANNOT_DETERMINE,
                reason="No transcript exists for this call.")
    assert f.citations == []


def test_valid_gap():
    f = Finding(check_id="Q1", account_id="A1", status=Status.GAP, severity="High",
                reason="Consent recorded 2 days after first WhatsApp message.", citations=[CITE])
    assert f.status is Status.GAP
