"""Notice dispatch tracker: notices sent, dispatch and service dates."""
from __future__ import annotations

from datetime import date


def get_notices(account_id: str, start: date | None = None, end: date | None = None) -> list[dict]:
    """Notices for an account with dispatch_date, service_date and notice type.

    TODO(owner): implement over staging.notice_dispatch.
    """
    raise NotImplementedError
