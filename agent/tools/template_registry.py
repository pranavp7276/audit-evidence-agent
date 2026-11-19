"""Template registry: approved message templates and the purpose each is sent for."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from agent.tools._common import query, with_citation


@lru_cache(maxsize=256)
def get_template(template_id: int | str, on: datetime | None = None) -> dict | None:
    """A message template: template_id, sms_category (COLLECTIONS, SERVICE or PROMOTIONAL), channel, subject.
    The registry keeps one version per template, so `on` is accepted but not used."""
    rows = query("SELECT template_id, sms_category, sms_dlt_id, digital_channel, template_subject FROM cn_core.digital_template WHERE template_id = %s", (int(template_id),))
    return with_citation(rows[0], "template_registry", "cn_core.digital_template", "template_id") if rows else None
