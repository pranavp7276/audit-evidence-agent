"""Certification register and collector roster: who was certified when."""
from __future__ import annotations

from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=4096)
def _certs(collector_id: str) -> tuple[dict, ...]:
    rows = query("SELECT * FROM staging.certifications WHERE collector_id = %s ORDER BY valid_from", (collector_id,))
    return tuple(with_citation(r, "cert_register", "raw.cert_register", "cert_id") for r in rows)


@lru_cache(maxsize=4096)
def _roster(collector_id: str) -> dict | None:
    rows = query("SELECT * FROM staging.collectors WHERE collector_id = %s", (collector_id,))
    return with_citation(rows[0], "collector_roster", "raw.collector_roster", "collector_id") if rows else None


def get_certifications(collector_id: str) -> list[dict]:
    """Certificates for a collector. Each row: cert_id, cert_name, valid_from, valid_to (inclusive
    dates), plus citation fields."""
    return list(_certs(collector_id))


def get_collector(collector_id: str) -> dict | None:
    """The collector's roster row, or None if the id is unknown."""
    return _roster(collector_id)
