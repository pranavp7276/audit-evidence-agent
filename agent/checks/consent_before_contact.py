from __future__ import annotations

from agent.checks.base import BaseCheck
from agent.contracts import Finding


class ConsentBeforeContactCheck(BaseCheck):
    """Every WhatsApp (or other consent-gated) message was preceded by valid consent for that channel.

    Test per message (subject_ref = message id):
      evidenced  consent_ts_utc < message_ts_utc, consent covers the channel, no withdrawal in between
      gap        no consent, consent after the message (late consent), or withdrawn before it
      cannot_determine  timestamps missing or zone of either source unknown
    Traps: consent captured after the first message but before later ones (gap only for the
    early ones); sources in different time zones (compare *_utc only); same-timestamp rule
    is in docs/decisions.md."""

    check_type = "consent_before_contact"

    def evaluate(self, account_id: str) -> list[Finding]:
        raise NotImplementedError
