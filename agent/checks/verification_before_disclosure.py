from __future__ import annotations

from agent.checks.base import BaseCheck, cite
from agent.contracts import Finding
from agent.db import read_rows
from agent.tools import get_contacts
from agent.tools._common import with_citation


def _verifications(account_id: str) -> dict[str, list[dict]]:
    rows = read_rows("SELECT * FROM staging.d11_verifications WHERE account_id = %s ORDER BY verified_ts_utc", (account_id,))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(r["contact_id"], []).append(with_citation(r, "D11", "raw.d11", "verification_id", "verified_ts"))
    return out


class VerificationBeforeDisclosureCheck(BaseCheck):
    """Identity was verified before any dues were disclosed on the call.

    Test per call where dues were disclosed (subject_ref = call id). There is no transcript store
    in this dataset (docs/decisions.md D-008), so disclosure is taken to happen at the call start
    in D4 and the verification record comes from D11:
      evidenced  a passed verification with verified_ts_utc before the call start
      gap        verification after disclosure, failed, or no verification at all
      cannot_determine  verification at exactly the call start (D-011)"""

    check_type = "verification_before_disclosure"

    def evaluate(self, account_id: str) -> list[Finding]:
        by_call = _verifications(account_id)
        gaps, oks, unknown = [], [], []
        for c in get_contacts(account_id, *self.window, channel="call"):
            if not (c["outcome"] == "connected" and c["dues_disclosed"]):
                continue
            call = cite(c, ("outcome", "dues_disclosed", "contact_ts_src"))
            fields = ("method", "result", "verified_ts_src")
            records = by_call.get(c["contact_id"], [])
            passed = [v for v in records if v["result"] == "passed"]
            if any(v["verified_ts_utc"] < c["contact_ts_utc"] for v in passed):
                v = next(v for v in passed if v["verified_ts_utc"] < c["contact_ts_utc"])
                oks.append((c["contact_id"],
                    f"Call {c['contact_id']}: identity verified ({v['verification_id']}) before dues were disclosed.",
                            [call, cite(v, fields, "supporting")]))
            elif any(v["verified_ts_utc"] == c["contact_ts_utc"] for v in passed):
                unknown.append((c["contact_id"], "Verification time equals the call start; whether that counts as 'before' "
                                                 "is not settled (docs/decisions.md D-011)."))
            else:
                why = ("only verified after disclosure" if passed else "verification failed" if records
                       else "no verification record exists")
                gaps.append((c["contact_id"],
                    f"Call {c['contact_id']} disclosed dues without prior identity verification: {why}.",
                             [call, *(cite(v, fields, "supporting") for v in records)]))
        return self.assemble(account_id, gaps, oks, unknown, "No connected calls with dues disclosed to test.")
