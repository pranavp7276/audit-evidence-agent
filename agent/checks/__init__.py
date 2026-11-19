"""Deterministic checks. The LLM decides which check applies and with what parameters;
the pass/fail judgement itself is code, so the same evidence always gives the same answer."""
from agent.checks.agent_certification import AgentCertificationCheck
from agent.checks.base import BaseCheck
from agent.checks.caller_id_registered import CallerIdRegisteredCheck
from agent.checks.calling_hours_frequency import CallingFrequencyCheck, CallingHoursCheck
from agent.checks.collector_active import CollectorActiveCheck
from agent.checks.consent_before_contact import ConsentBeforeContactCheck
from agent.checks.notice_timeline import NoticeTimelineCheck
from agent.checks.recording_completeness import RecordingCompletenessCheck
from agent.checks.template_approval import TemplateApprovalCheck
from agent.checks.third_party_disclosure import ThirdPartyDisclosureCheck
from agent.checks.verification_before_disclosure import VerificationBeforeDisclosureCheck
from agent.core.contracts import CheckType

REGISTRY: dict[CheckType, type[BaseCheck]] = {
    CheckType.CONSENT_BEFORE_CONTACT: ConsentBeforeContactCheck,
    CheckType.CALLING_HOURS: CallingHoursCheck,
    CheckType.CALLING_FREQUENCY: CallingFrequencyCheck,
    CheckType.VERIFICATION_BEFORE_DISCLOSURE: VerificationBeforeDisclosureCheck,
    CheckType.NOTICE_TIMELINE: NoticeTimelineCheck,
    CheckType.AGENT_CERTIFICATION: AgentCertificationCheck,
    CheckType.RECORDING_COMPLETENESS: RecordingCompletenessCheck,
    CheckType.TEMPLATE_APPROVAL: TemplateApprovalCheck,
    CheckType.COLLECTOR_ACTIVE: CollectorActiveCheck,
    CheckType.CALLER_ID_REGISTERED: CallerIdRegisteredCheck,
    CheckType.THIRD_PARTY_DISCLOSURE: ThirdPartyDisclosureCheck,
}

__all__ = ["REGISTRY", "BaseCheck"]
