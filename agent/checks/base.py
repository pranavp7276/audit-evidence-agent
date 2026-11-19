from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from agent.contracts import CheckSpec, Citation, Finding, Status

RULE_TZ = ZoneInfo("Asia/Kolkata")  # zone D12 hours/limits and the cert register use (docs/decisions.md D-009)

Event = tuple[str, str, list[Citation]]  # (subject_ref, reason, citations)


def mask(number: str | None) -> str:
    """A phone number with all but the last four digits hidden, for text that goes into reasons and letters."""
    return "n/a" if not number else "X" * max(len(number) - 4, 0) + number[-4:]


def _plain(v):
    return v if v is None or isinstance(v, (str, int, float, bool)) else (v.isoformat() if hasattr(v, "isoformat") else str(v))


def cite(row: dict, fields: tuple[str, ...] = (), role: str = "primary") -> Citation:
    """A Citation from a tool row; `fields` are the only columns copied into the extract (data minimisation)."""
    return Citation(
        source_system=row["source_system"], source_table=row["source_table"], record_key=row["record_key"],
        record_ts_utc=row["record_ts_utc"], record_ts_original=row["record_ts_original"],
        extract={k: _plain(row[k]) for k in fields} or None, role=role)


class BaseCheck(ABC):
    """Every check takes a spec and the sampled accounts and returns one or more Findings per
    account. It never returns nothing for an account: if it cannot decide, it says so."""

    check_type: str

    def __init__(self, spec: CheckSpec, severity_scale: list[str]):
        self.spec = spec
        self.severity_scale = severity_scale

    @property
    def severity(self) -> str:
        """Severity for this check's gaps: the request's label for the question, else its most severe label."""
        return self.spec.test.get("severity") or (self.severity_scale[0] if self.severity_scale else "Unrated")

    @property
    def window(self) -> tuple[datetime | None, datetime | None]:
        """The audit period as UTC bounds [start, end), or (None, None) when the request names no period.
        The period is India calendar days, start inclusive and end exclusive (docs/decisions.md D-014)."""
        p = self.spec.test.get("period")
        if not p:
            return None, None

        def bound(iso: str) -> datetime:
            return datetime.combine(date.fromisoformat(iso), time.min, tzinfo=RULE_TZ).astimezone(UTC)

        return bound(p["start"]), bound(p["end"])

    @abstractmethod
    def evaluate(self, account_id: str) -> list[Finding]:
        """Test one account. Must cite the records behind every evidenced or gap finding."""

    def run(self, account_ids: list[str]) -> list[Finding]:
        findings: list[Finding] = []
        for account_id in account_ids:
            try:
                result = self.evaluate(account_id)
            except NotImplementedError:
                raise
            except Exception as exc:  # a crash is never a pass
                result = [self.cannot_determine(account_id, f"Check failed to run: {exc!r}")]
            if not result:
                result = [self.cannot_determine(account_id, "No records found to test this check.")]
            findings.extend(result)
        return findings

    def cannot_determine(self, account_id: str, reason: str, subject_ref: str | None = None) -> Finding:
        return Finding(check_id=self.spec.check_id, account_id=account_id, subject_ref=subject_ref,
                       status=Status.CANNOT_DETERMINE, reason=reason)

    def assemble(self, account_id: str, gaps: list[Event], oks: list[Event],
                 unknown: list[tuple[str, str]], nothing: str) -> list[Finding]:
        """Per-event results to findings: one gap per breaching event; otherwise one evidenced finding
        for the account (citing every record tested) plus a cannot_determine per undecidable event.
        Gaps are never merged or dropped."""
        if gaps:
            return [Finding(check_id=self.spec.check_id, account_id=account_id, subject_ref=s, status=Status.GAP,
                            severity=self.severity, reason=r, citations=c) for s, r, c in gaps]
        out = [self.cannot_determine(account_id, r, s) for s, r in unknown]
        if oks:
            out.append(Finding(
                check_id=self.spec.check_id, account_id=account_id, status=Status.EVIDENCED,
                reason=f"All {len(oks)} tested event(s) passed. " + " ".join(r for _, r, _ in oks[:3])
                       + (" ..." if len(oks) > 3 else ""),
                citations=[c for _, _, cs in oks for c in cs]))
        return out or [self.cannot_determine(account_id, nothing)]
