from __future__ import annotations

from agent.checks.base import BaseCheck, cite, mask
from agent.contracts import Finding
from agent.tools import get_consents, get_messages
from agent.tools.contact_log import SENT_STATUSES

_MSG = ("channel", "contact_no", "category", "template_id", "sent_ts_src", "sent_ts_src_tz")
_CONSENT = ("channel", "contact_no", "purpose", "status", "effective_ts_src")


class ConsentBeforeContactCheck(BaseCheck):
    """Every WhatsApp or SMS message sent was preceded by valid consent for that recipient, channel and purpose.

    Test per message sent (subject_ref = message id): replay the recipient's consent history up to the send time (UTC).
    The purpose needed is the template's category (a COLLECTIONS consent also covers SERVICE messages, but not PROMOTIONAL).
      evidenced  the needed purpose was granted and not revoked before the message
      gap        no consent for this number and channel, consent only for another purpose, consent withdrawn before the
                 message, or consent recorded only after it
      cannot_determine  a consent event at exactly the message time (the tie is not settled, docs/decisions.md D-011)
    Messages that failed to send are not tested. The two sources are in different zones: compare *_utc only."""

    check_type = "consent_before_contact"
    tools = ('message_log', 'consent_registry')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        channels = self.spec.test.get("channels", ["WHATSAPP", "SMS"])
        gaps, oks, unknown = [], [], []
        for m in get_messages(account_id, *self.window):
            if m["channel"] not in channels or m["status"] not in SENT_STATUSES:
                continue
            need = m["category"] or "COLLECTIONS"
            history = get_consents(m["contact_no"], m["channel"])
            before = [c for c in history if c["effective_ts_utc"] < m["sent_ts_utc"]]
            tie = [c for c in history if c["effective_ts_utc"] == m["sent_ts_utc"]]
            granted: dict[str, dict] = {}
            withdrawn: dict[str, dict] = {}
            for c in before:
                if c["status"] == "GRANTED":
                    granted[c["purpose"]] = c
                    withdrawn.pop(c["purpose"], None)
                else:
                    granted.pop(c["purpose"], None)
                    withdrawn[c["purpose"]] = c
            covering = granted.get(need) or (granted.get("COLLECTIONS") if need == "SERVICE" else None)
            msg = cite(m, _MSG)
            who = f"{m['channel'].title()} message {m['message_id']} to {mask(m['contact_no'])}"
            if covering:
                oks.append((m["message_id"], f"{who} ({need.lower()}) had consent {covering['consent_id']} first.",
                            [msg, cite(covering, _CONSENT, "supporting")]))
            elif tie:
                unknown.append((m["message_id"], f"{who}: a consent event is timestamped exactly when the message was sent; whether that counts as "
                                                 "'before' is not settled (docs/decisions.md D-011)."))
            else:
                if need in withdrawn:
                    why, support = f"consent for {need.lower()} was withdrawn before it", [withdrawn[need]]
                elif granted:
                    why, support = f"the number only had consent for {', '.join(p.lower() for p in granted)}, not {need.lower()}", list(granted.values())
                else:
                    later = [c for c in history if c["effective_ts_utc"] > m["sent_ts_utc"]]
                    why, support = (("consent was only recorded after it", later[:1]) if later else ("no consent on file for this number and channel", []))
                gaps.append((m["message_id"], f"{who} was sent without valid consent: {why}.", [msg, *(cite(c, _CONSENT, "supporting") for c in support)]))
        return self.assemble(account_id, gaps, oks, unknown, "No WhatsApp or SMS messages sent in the period to test.")
