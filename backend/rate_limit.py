"""Rate limiting (SlowAPI). Uses Redis when a broker/Redis URL is configured.

Policy (Phase P2):
- **General API rate limits**: Redis-backed when ``REDIS_URL`` / ``CELERY_BROKER_URL``
  is set, with ``in_memory_fallback_enabled=True`` so a brief Redis outage does
  **not** crash request handling (fail-open → local counters).
- **Login lockout** (``backend/auth.py``): prefers Redis; on Redis failure falls
  back to in-process counters so lockouts still apply on that worker. Prefer
  fail-closed for login abuse: SlowAPI still enforces ``5/minute`` on
  ``/auth/login`` via memory fallback when Redis is down.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from .services.redis_url import redis_url


def _build_limiter() -> Limiter:
    url = redis_url()
    if url:
        # Shared counters across API replicas. Fall back to memory if Redis blips.
        return Limiter(
            key_func=get_remote_address,
            storage_uri=url,
            in_memory_fallback_enabled=True,
        )
    return Limiter(key_func=get_remote_address)


limiter = _build_limiter()
