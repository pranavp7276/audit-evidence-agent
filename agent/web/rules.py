"""Plain-language descriptions an auditor can read and defend: what each check tests, which sources it reads,
how time zones are treated, and the interpretations the platform has assumed (docs/decisions.md)."""
from __future__ import annotations

CHECK_INFO: dict[str, dict] = {
    "consent_before_contact": {
        "title": "Consent before contact",
        "tests": "Every WhatsApp or SMS message sent was preceded by valid consent for that recipient number, channel and purpose (collections, service or promotional).",
        "gap": "No consent for that number and channel, consent only for a different purpose, consent withdrawn before the message, or consent recorded only after it.",
        "unknown": "A consent event is timestamped at exactly the same instant as the message (the tie is not settled).",
        "sources": ["CN Core message log", "Consent registry", "Template registry"],
        "limits": None,
    },
    "calling_hours": {
        "title": "Calls within permitted hours",
        "tests": "Every outbound call attempt started inside the calling window in force on that date, in the borrower's local time (IST). The dialer's own timestamp is converted first.",
        "gap": "A call started before the window opens or at or after it closes, using the window effective on that date.",
        "unknown": "None expected.",
        "sources": ["CN Core call log (SlashRTC, CognifAI)", "D12 policy rules"],
        "limits": ["calling_window_start", "calling_window_end"],
    },
    "calling_frequency": {
        "title": "Call frequency within the limit",
        "tests": "No contact number received more outbound call attempts in one calendar day (IST) than the cap in force that day. A session with several status rows, and a call mirrored in both dialers, counts once.",
        "gap": "A day with more eligible attempts to one number than the cap. The first call past the cap is cited, with the others and the rule.",
        "unknown": "None expected.",
        "sources": ["CN Core call log (SlashRTC, CognifAI)", "D12 policy rules"],
        "limits": ["max_attempts_per_contact_per_day"],
    },
    "verification_before_disclosure": {
        "title": "Identity verified before dues disclosed",
        "tests": "On every connected outbound call where dues were disclosed, a passed identity check comes earlier in the recording than the first disclosure.",
        "gap": "Disclosure before the identity check, a failed check, or no identity check at all.",
        "unknown": "The recording is missing or could not be read, there is no transcript, the identity step is unclear, or the check is at exactly the disclosure offset.",
        "sources": ["CN Core call log", "Recording store", "Transcript store"],
        "limits": None,
    },
    "notice_timeline": {
        "title": "Notices dispatched and served on time",
        "tests": "Each notice was dispatched, and served, within the business days allowed from its trigger date (Mon-Fri, national holidays excluded; day N is inside the limit).",
        "gap": "Dispatched or served late, or not dispatched or served although the deadline has passed.",
        "unknown": "A deadline has not passed yet. An account with no notice on file has nothing to test and is shown as cannot determine.",
        "sources": ["Notice dispatch history", "Holiday calendar", "D12 policy rules"],
        "limits": ["notice_dispatch_sla_business_days", "notice_service_sla_business_days"],
    },
    "agent_certification": {
        "title": "Recovery agent certified on the call date",
        "tests": "The collector held a valid certificate on the date of every outbound call they made. The call log names the collector by user; the register by employee code, so they are joined through the user record.",
        "gap": "The certificate had expired, had not started, or the register has none for that employee code.",
        "unknown": "The collector has no employee code on file, so they cannot be matched to the register.",
        "sources": ["CN Core call log", "Certification register", "Collector roster"],
        "limits": None,
    },
    "recording_completeness": {
        "title": "Recording available for every connected call",
        "tests": "Every connected outbound call has a recording in the recording store.",
        "gap": "The recording store confirms it holds no recording for the call (NOT_FOUND).",
        "unknown": "The recording store could not be read (RETRIEVAL_FAILED): the recording may exist.",
        "sources": ["CN Core call log", "Recording store"],
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
    "gap": "Records show a breach (or a mandatory record is confirmed missing). Reported as found, graded on the request's severity scale, and cited.",
    "cannot_determine": "The evidence is missing, unreadable or ambiguous, so the platform makes no claim either way. These need manual follow-up.",
}

ASSUMPTIONS = [
    ("Time zones", "Every timestamp is compared in UTC. SlashRTC logs call times in IST and CognifAI in UTC; the message log is IST; the consent registry is UTC. "
                   "The original value and its zone are shown beside the UTC one wherever a record is cited."),
    ("One call, one count", "A call session is identified by its dialer and session id. Several status rows (for example connected, then disposed) are kept as "
                            "evidence but the call counts once. A call mirrored in both dialers counts under the dialer the cross-reference names."),
    ("Calling hours and limits", "Taken from D12 and effective-dated: each call is tested against the rule in force on its own date, so a rule change does not "
                                 "rewrite history. Hours are measured in borrower local time (IST). The start of the window is inclusive, the end exclusive."),
    ("Calling frequency", "Eligible attempts are outbound call sessions to the same contact number on one IST calendar day, across both dialers and both calling "
                          "modes. System failures and inbound calls are not attempts."),
    ("Consent", "Consent is per recipient number, channel and purpose. A COLLECTIONS consent also covers SERVICE messages, not PROMOTIONAL. Messages that failed "
                "to send are not tested."),
    ("Exact ties", "A consent, or a verification, at exactly the same instant as the message or the disclosure is reported as cannot determine."),
    ("Dues disclosure", "Disclosure and identity checks are read from timestamped transcript segments. Without a readable recording and transcript the "
                        "result is cannot determine, never a pass."),
    ("Notice timeline", "Business days are Monday to Friday excluding national holidays, from the trigger date. Dispatch and service are each tested "
                        "against the rule in force on the trigger date. The deadline day itself is inside the limit."),
    ("Certificates", "Valid from and valid to dates are both inclusive. The call date is the IST date. The register is keyed by employee code."),
    ("Account references", "References in a request are matched to CN loan accounts by loan account number or CN account id. A reference that matches "
                           "nothing, or more than one loan, stays visible and is not tested until Compliance resolves it."),
    ("Gaps are never softened", "Disputing a gap in review adds a note; it does not remove the gap from the report or the letter."),
    ("Request interpretation", "Questions are mapped to checks before the run and the auditor confirms the mapping. A question that fits no check is reported as unanswered."),
]

# staging view, timestamp column, time zone of the source, human label
SOURCES = [
    ("CN Core call sessions (SlashRTC, CognifAI)", "staging.call_sessions", "started_ts_utc", "SlashRTC IST, CognifAI UTC"),
    ("CN Core message log (WhatsApp, SMS)", "staging.messages", "sent_ts_utc", "Asia/Kolkata"),
    ("Consent registry", "staging.consents", "effective_ts_utc", "UTC"),
    ("Recording store (status)", "staging.recordings", None, "n/a"),
    ("Transcript segments", "staging.transcript_segments", None, "offsets into the recording"),
    ("D12 policy rules", "staging.policy_rules", "effective_from", "effective dates"),
    ("Notice dispatch history", "staging.notices", "trigger_date", "calendar dates (India)"),
    ("Holiday calendar", "staging.holidays", "holiday_date", "calendar dates"),
    ("Collector roster (users)", "staging.collectors", None, "n/a"),
    ("Certification register", "staging.certifications", "valid_from", "calendar dates"),
    ("Loan accounts", "staging.accounts", None, "n/a"),
]
