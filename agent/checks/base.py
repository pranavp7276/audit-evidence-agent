from __future__ import annotations

from abc import ABC, abstractmethod

from agent.contracts import CheckSpec, Finding, Status


class BaseCheck(ABC):
    """Every check takes a spec and the sampled accounts and returns one or more Findings per
    account. It never returns nothing for an account: if it cannot decide, it says so."""

    check_type: str

    def __init__(self, spec: CheckSpec, severity_scale: list[str]):
        self.spec = spec
        self.severity_scale = severity_scale

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
