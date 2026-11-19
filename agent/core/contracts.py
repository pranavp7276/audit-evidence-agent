"""The shared contracts. Everything that crosses a team boundary goes through these types.

  parser  --CheckSpec-->  checks  --Finding(+Citation)-->  store  --audit.*-->  pack / eval

Change these only with a PR that every module owner reviews, and log it in docs/decisions.md.
The rules here mirror the database constraints in db/migrations/V002__audit.sql, so a bad
finding fails in Python before it ever reaches the database.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CheckType(str, Enum):
    CONSENT_BEFORE_CONTACT = "consent_before_contact"
    CALLING_HOURS = "calling_hours"
    CALLING_FREQUENCY = "calling_frequency"
    VERIFICATION_BEFORE_DISCLOSURE = "verification_before_disclosure"
    NOTICE_TIMELINE = "notice_timeline"
    AGENT_CERTIFICATION = "agent_certification"
    RECORDING_COMPLETENESS = "recording_completeness"
    TEMPLATE_APPROVAL = "template_approval"
    COLLECTOR_ACTIVE = "collector_active"
    CALLER_ID_REGISTERED = "caller_id_registered"
    THIRD_PARTY_DISCLOSURE = "third_party_disclosure"
    OTHER = "other"


class Status(str, Enum):
    EVIDENCED = "evidenced"
    GAP = "gap"
    CANNOT_DETERMINE = "cannot_determine"


class SourceSystem(str, Enum):
    D4 = "D4"
    D5 = "D5"
    D10 = "D10"
    D11 = "D11"
    D12 = "D12"
    NOTICE_DISPATCH = "notice_dispatch"
    CERT_REGISTER = "cert_register"
    COLLECTOR_ROSTER = "collector_roster"
    HOLIDAY_CALENDAR = "holiday_calendar"
    TEMPLATE_REGISTRY = "template_registry"
    RECORDING_STORE = "recording_store"
    TRANSCRIPT_STORE = "transcript_store"
    CONSENT_REGISTRY = "consent_registry"
    CONTACT_LOG = "contact_log"
    CALLER_ID_REGISTRY = "caller_id_registry"


class Request(BaseModel):
    """An audit request as received."""
    request_id: str
    source: str = Field(pattern="^(pdf|email|text)$")
    path: str | None = None
    text: str
    severity_scale: list[str] = Field(
        default_factory=list,
        description="Severity labels exactly as the request gives them, most severe first.")


class CheckSpec(BaseModel):
    """One testable check derived from (part of) a request question."""
    check_id: str = Field(description="Stable within a run, e.g. 'Q3b'.")
    question_ref: str = Field(description="Where in the request it came from, e.g. 'Q3'.")
    question_text: str = Field(description="The exact wording this check was derived from.")
    check_type: CheckType
    sample: dict[str, Any] = Field(
        description="How accounts are chosen: an explicit account list, or a filter + period.")
    test: dict[str, Any] = Field(
        description="What passes, in plain words plus parameters (e.g. window, limits source).")
    sources: list[SourceSystem]


class Citation(BaseModel):
    """A pointer to the exact record a statement rests on."""
    source_system: SourceSystem
    source_table: str = Field(description="schema.table the record lives in, e.g. compliance.notice.")
    record_key: str = Field(description="Natural key, or the raw _row_no.")
    record_ts_utc: datetime | None = None
    record_ts_original: str | None = Field(
        default=None, description="The same timestamp as written in the source, untouched.")
    extract: dict[str, Any] | None = Field(
        default=None, description="Only the fields the request needs. No extra borrower data.")
    role: str = Field(default="primary", pattern="^(primary|supporting)$")


class Finding(BaseModel):
    """The result of testing one check on one account (or one event within it)."""
    check_id: str
    account_id: str
    subject_ref: str | None = Field(
        default=None, description="The event tested if finer than the account: message id, call id.")
    status: Status
    severity: str | None = None
    reason: str = Field(min_length=10, description="Plain statement of what was found. No softening.")
    citations: list[Citation] = Field(default_factory=list)
    evidence_query: str | None = None

    @model_validator(mode="after")
    def _guardrails(self) -> "Finding":
        if self.status in (Status.EVIDENCED, Status.GAP) and not self.citations:
            raise ValueError(
                f"{self.status.value} finding for {self.check_id}/{self.account_id} has no citation. "
                "No claim without a cited record: cite it, or mark it cannot_determine.")
        if self.status is Status.GAP and not self.severity:
            raise ValueError(f"gap finding for {self.check_id}/{self.account_id} needs a severity.")
        return self
