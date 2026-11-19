from __future__ import annotations

from datetime import UTC

from agent.checks.base import BaseCheck, cite, mask
from agent.core.contracts import Finding
from agent.tools import get_messages, get_template
from agent.tools.contact_log import SENT_STATUSES

_MSG = ("channel", "template_id", "sent_ts_src", "sent_ts_src_tz")
_TPL = ("template_id", "sms_category", "digital_channel", "approval_status", "approved_at", "retired_at")


class TemplateApprovalCheck(BaseCheck):
    """Every WhatsApp or SMS message was sent on a template that was approved, and not yet retired, when it was sent (catalog TPL-01).

    Test per message sent (subject_ref = message id), comparing the send time (UTC) with the template registry:
      evidenced  the template is APPROVED, approved_at <= sent time, and not retired (retired_at empty or after the send)
      gap        no template on record for the message, the template is pending, rejected or expired, it was approved only after the
                 message was sent, or it had been retired before it
    Messages that failed to send are not tested. A registry timestamp has no zone; it is read as UTC (the registry's own clock)."""

    check_type = "template_approval"
    tools = ('message_log', 'template_registry')  # what the planner schedules and the trace attributes

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks = [], []
        for m in get_messages(account_id, *self.window):
            if m["status"] not in SENT_STATUSES:
                continue
            tpl = get_template(m["template_id"]) if m["template_id"] is not None else None
            who = f"{m['channel'].title()} message {m['message_id']} to {mask(m['contact_no'])}"
            msg = cite(m, _MSG)
            if tpl is None:
                gaps.append((m["message_id"], f"{who} has no template on record, so it cannot have been sent on an approved one.", [msg]))
                continue
            sent, status = m["sent_ts_utc"], tpl["approval_status"]
            approved = tpl["approved_at"].replace(tzinfo=UTC) if tpl["approved_at"] else None
            retired = tpl["retired_at"].replace(tzinfo=UTC) if tpl["retired_at"] else None
            cites = [msg, cite(tpl, _TPL, "supporting")]
            if status != "APPROVED" or approved is None:
                gaps.append((m["message_id"], f"{who} was sent on template {tpl['template_id']}, which is {status.lower()} in the registry.", cites))
            elif approved > sent:
                gaps.append((m["message_id"], f"{who} was sent on template {tpl['template_id']} before the template was approved (approved {approved:%Y-%m-%d}).", cites))
            elif retired is not None and sent >= retired:
                gaps.append((m["message_id"], f"{who} was sent on template {tpl['template_id']} after the template was retired ({retired:%Y-%m-%d}).", cites))
            else:
                oks.append((m["message_id"], f"{who} was sent on template {tpl['template_id']}, approved {approved:%Y-%m-%d}.", cites))
        return self.assemble(account_id, gaps, oks, [], "No WhatsApp or SMS messages sent in the period to test.")
