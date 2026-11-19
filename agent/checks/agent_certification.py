from __future__ import annotations

from agent.checks.base import RULE_TZ, BaseCheck, cite
from agent.contracts import Finding
from agent.tools import get_certifications, get_contacts
from agent.tools.certification_register import get_collector


class AgentCertificationCheck(BaseCheck):
    """The collector held a valid certificate on the date of each call they made.

    Test per call (subject_ref = call id): call date (in the zone the register uses) within
    [valid_from, valid_to] of some certificate for that collector_id.
    gap if expired / not yet valid / no certificate. Cite the call row and the certificate row
    (or the roster row, if no certificate exists)."""

    check_type = "agent_certification"

    def evaluate(self, account_id: str) -> list[Finding]:
        gaps, oks = [], []
        for c in get_contacts(account_id, channel="call"):
            day = c["contact_ts_utc"].astimezone(RULE_TZ).date()
            certs = get_certifications(c["collector_id"])
            valid = [x for x in certs if x["valid_from"] <= day <= x["valid_to"]]
            call = cite(c, ("collector_id", "contact_ts_src"))
            fields = ("collector_id", "cert_name", "valid_from", "valid_to")
            if valid:
                oks.append((c["contact_id"], f"Collector {c['collector_id']} was certified on {day} for call {c['contact_id']}.",
                            [call, cite(valid[0], fields, "supporting")]))
            else:
                support = ([cite(x, fields, "supporting") for x in certs] or
                           ([cite(r, ("collector_id", "status"),
                               "supporting")] if (r := get_collector(c["collector_id"])) else []))
                gaps.append((c["contact_id"], f"Collector {c['collector_id']} held no valid certificate on {day} "
                                              f"when call {c['contact_id']} was made.", [call, *support]))
        return self.assemble(account_id, gaps, oks, [], "No calls in the contact log to test.")
