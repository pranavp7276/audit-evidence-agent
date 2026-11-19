"""Template registry: message templates, the purpose each is sent for, and when each was approved and retired."""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache

from agent.core.toolkit import tool
from agent.tools._common import query, with_citation


@lru_cache(maxsize=512)
@tool("template_registry", sources=("Template registry",))
def get_template(template_id: int | str, on: datetime | None = None) -> dict | None:
    """A message template: template_id, sms_category (COLLECTIONS, SERVICE or PROMOTIONAL), digital_channel, approval_status (APPROVED, PENDING,
    REJECTED or EXPIRED), approved_at and retired_at (UTC; empty when never approved or not retired). None if the template id is unknown.
    The registry keeps one version per template, so `on` is accepted but not used."""
    rows = query("SELECT * FROM staging.templates WHERE template_id = %s", (str(int(template_id)),))
    return with_citation(rows[0], "template_registry", "cn_core.digital_template", "template_id") if rows else None
