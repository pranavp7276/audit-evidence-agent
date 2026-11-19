from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_consents, get_contacts


class ConsentBeforeContactCheck(BaseCheck):
    """Every WhatsApp (or other consent-gated) message was preceded by valid consent for that channel.

    Test per message (subject_ref = message id):
      evidenced  consent_ts_utc < message_ts_utc, consent covers the channel, no withdrawal in between
      gap        no consent, consent after the message (late consent), or withdrawn before it
      cannot_determine  timestamps missing or zone of either source unknown
    Traps: consent captured after the first message but before later ones (gap only for the
    early ones); sources in different time zones (compare *_utc only); same-timestamp rule
    is in docs/decisions.md (D-011: an exact tie is cannot_determine)."""

    check_type = "consent_before_contact"

    def evaluate(self, account_id: str) -> list[Finding]:
        channels = self.spec.test.get("channels", ["whatsapp", "sms"])
        gaps, oks, unknown = [], [], []
        for m in (c for c in get_contacts(account_id) if c["channel"] in channels):
            msg = cite(m, ("channel", "contact_ts_src"))
            records = get_consents(account_id, m["channel"])
            before = [c for c in records if c["consent_ts_utc"] < m["contact_ts_utc"]]
            if any(c["consent_ts_utc"] == m["contact_ts_utc"] for c in records) and not before:
                unknown.append((m["contact_id"], "Consent timestamp equals the message timestamp; whether that counts as "
                                                 "'before' is not settled (docs/decisions.md D-011)."))
            elif before and before[-1]["status"] == "granted":
                oks.append((m["contact_id"],
                    f"{m['channel']} message {m['contact_id']} had consent {before[-1]['consent_id']} first.",
                            [msg, cite(before[-1], ("channel", "status", "consent_ts_src"), "supporting")]))
            else:
                later = [cite(c, ("channel", "status", "consent_ts_src"), "supporting") for c in records[len(before):][:1]]
                why = ("consent was withdrawn before it" if before else
                       "consent was only recorded after it" if later else "no consent record exists")
                gaps.append((m["contact_id"], f"{m['channel']} message {m['contact_id']} was sent without prior consent: {why}.",
                             [msg, *later]))
        return self.assemble(account_id, gaps, oks, unknown, "No WhatsApp or SMS messages in the contact log to test.")
