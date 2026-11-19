"""Certification register and collector roster."""
from __future__ import annotations


def get_certifications(collector_id: str) -> list[dict]:
    """All certificate rows for a collector, each with valid_from and valid_to (dates).

    TODO(owner): implement over staging.cert_register joined to staging.collector_roster.
    """
    raise NotImplementedError
