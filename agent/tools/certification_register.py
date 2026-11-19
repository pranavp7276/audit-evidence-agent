"""Certification register and collector roster. The contact log knows a collector by user id; the register by employee code."""
from __future__ import annotations

from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _certs(employee_code: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.certifications WHERE employee_code = %s ORDER BY valid_from", (employee_code,))
    return tuple(with_citation(r, "cert_register", "compliance.collector_certification", "cert_id") for r in rows)


@lru_cache(maxsize=4096)
def _collector(user_id: str) -> dict | None:
    rows = query("SELECT * FROM staging.collectors WHERE user_id = %s", (str(user_id),))
    return with_citation(rows[0], "collector_roster", "uamdb.users", "user_id") if rows else None


def get_certifications(employee_code: str) -> list[dict]:
    """Certificates for a collector by employee code. Each row: cert_id, certification, certificate_no, valid_from,
    valid_to (both inclusive dates), plus citation fields."""
    return list(_certs(employee_code))


def get_collector(user_id: int | str) -> dict | None:
    """The collector's roster row (employee_code, agency, status), or None if the user id is unknown."""
    return _collector(str(user_id))
