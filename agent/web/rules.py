"""Plain-language descriptions an auditor can read and defend: what each check tests, which sources it reads,
how time zones are treated, and the interpretations the platform has assumed (docs/decisions.md)."""
from __future__ import annotations

CHECK_INFO: dict[str, dict] = {
    "consent_before_contact": {
        "title": "Consent before contact",
        "tests": "Every WhatsApp or SMS message was preceded by a granted consent record for the same account and channel.",
        "gap": "No consent on file, consent captured after the message, or consent withdrawn before it.",
        "unknown": "The consent was recorded at exactly the same instant as the message (the tie is not settled).",
        "sources": ["D4 contact log", "D5 consent registry"],
        "limits": None,
    },
    "calling_hours": {
        "title": "Calls within permitted hours",
        "tests": "Every call was placed inside the permitted calling window, in the borrower's local time (IST).",
        "gap": "A call placed before the window opens or at/after it closes.",
        "unknown": "None expected.",
        "sources": ["D4 contact log", "D12 policy limits"],
        "limits": ["calling_hours_start", "calling_hours_end"],
    },
    "calling_frequency": {
        "title": "Call frequency within the limit",
        "tests": "No account received more call attempts in one calendar day (IST) than the limit.",
        "gap": "A day with more attempts than the limit. All calls of that day are cited.",
        "unknown": "None expected.",
        "sources": ["D4 contact log", "D12 policy limits"],
        "limits": ["max_calls_per_day"],
    },
    "verification_before_disclosure": {
        "title": "Identity verified before dues disclosed",
        "tests": "On every connected call where dues were disclosed, a passed identity verification precedes the call's disclosure.",
        "gap": "Verification only after disclosure, a failed verification, or no verification record.",
        "unknown": "Verification at exactly the call start (the tie is not settled).",
        "sources": ["D4 contact log", "D11 identity verification"],
        "limits": None,
    },
    "notice_timeline": {
        "title": "Notices served on time",
        "tests": "Each notice was served within the allowed number of business days from its trigger date.",
        "gap": "Served after the allowed business days, or never served.",
        "unknown": "None expected. An account with no notice on file has nothing to test and is shown as cannot determine.",
        "sources": ["Notice dispatch history", "Holiday calendar", "D12 policy limits"],
        "limits": ["notice_sla_business_days"],
    },
    "agent_certification": {
        "title": "Recovery agent certified on the call date",
        "tests": "The collector held a valid certificate on the date of every call they made.",
        "gap": "Certificate expired, not yet valid or never issued on the call date.",
        "unknown": "None expected.",
        "sources": ["D4 contact log", "Certification register", "Collector roster"],
        "limits": None,
    },
    "recording_completeness": {
        "title": "Recording available for every connected call",
        "tests": "Every connected call has a recording in the recording store.",
        "gap": "A connected call with no recording.",
        "unknown": "None expected.",
        "sources": ["D4 contact log", "D10 recording store"],
        "limits": None,
    },
    "other": {
        "title": "Not testable by the platform",
        "tests": "This question could not be mapped to a test. It is reported in the response as unanswered, never dropped.",
        "gap": "n/a",
        "unknown": "n/a",
        "sources": [],
        "limits": None,
    },
}

STATUS_MEANING = {
    "evidenced": "Records were found that prove compliance for every event tested. Every evidenced result cites its records.",
    "gap": "Records show a breach (or the evidence that should exist is missing). Reported as found, graded on the request's severity scale, and cited.",
    "cannot_determine": "The evidence is missing or ambiguous, so the platform makes no claim either way. These need manual follow-up.",
}

ASSUMPTIONS = [
    ("Time zones", "Every timestamp is compared in UTC. The contact log, recording store and notice dates are Asia/Kolkata; "
                   "the consent registry and identity verification are UTC. The original value of each timestamp is shown next to the UTC one."),
    ("Calling hours and limits", "Taken from D12 (never hard-coded). Hours are measured in borrower local time, which is IST for every account in this data. "
                                 "The start of the window is inclusive and the end is exclusive."),
    ("Calling frequency", "Every call attempt counts (connected or not), per calendar day in IST."),
    ("Exact ties", "A consent or verification at exactly the same instant as the message or call is reported as cannot determine, not as a pass or a gap."),
    ("Dues disclosure", "There is no transcript store in this data, so dues are taken to be disclosed at the start of the call recorded in the contact log."),
    ("Notice timeline", "Business days are Monday to Friday excluding national holidays, counted from the trigger date to the service date."),
    ("Certificates", "Valid from and valid to dates are both inclusive. The call date is taken in IST."),
    ("Gaps are never softened", "Disputing a gap in review adds a note; it does not remove the gap from the report or the letter."),
    ("Request interpretation", "Questions are mapped to checks before the run and the auditor confirms the mapping. A question that fits no check is reported as unanswered."),
]

# staging view, timestamp column, time zone of the source, human label
SOURCES = [
    ("D4 contact log", "staging.d4_contacts", "contact_ts_utc", "Asia/Kolkata"),
    ("D5 consent registry", "staging.d5_consents", "consent_ts_utc", "UTC"),
    ("D10 recording store", "staging.d10_recordings", "recorded_ts_utc", "Asia/Kolkata"),
    ("D11 identity verification", "staging.d11_verifications", "verified_ts_utc", "UTC"),
    ("D12 policy limits", "staging.d12_policy", None, "n/a"),
    ("Notice dispatch history", "staging.notices", "trigger_date", "calendar dates (India)"),
    ("Holiday calendar", "staging.holidays", "holiday_date", "calendar dates"),
    ("Collector roster", "staging.collectors", None, "n/a"),
    ("Certification register", "staging.certifications", "valid_from", "calendar dates"),
]
