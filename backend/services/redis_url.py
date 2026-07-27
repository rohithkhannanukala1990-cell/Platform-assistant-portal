"""Shared Redis URL resolution for lockout, rate limits, and Celery."""

from __future__ import annotations

import os
from typing import Optional


def redis_url() -> Optional[str]:
    """Return Redis URL for shared lockout/rate-limit state when configured.

    Preference: ``RATELIMIT_STORAGE_URL``, then ``CELERY_BROKER_URL``, then ``REDIS_URL``.
    """
    for key in ("RATELIMIT_STORAGE_URL", "CELERY_BROKER_URL", "REDIS_URL"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return None
