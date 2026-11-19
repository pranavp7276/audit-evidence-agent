"""Template registry: approved message templates and their validity."""
from __future__ import annotations

from datetime import datetime


def get_template(template_id: str, on: datetime | None = None) -> dict | None:
    """The template version in force at a given time. There is no template registry in this
    dataset, so this returns None; D4 only carries the template id."""
    return None
