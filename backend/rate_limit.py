"""Rate limiting (SlowAPI). Uses Redis when a broker/Redis URL is configured."""

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
