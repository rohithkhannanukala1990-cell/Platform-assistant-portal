"""Shared idempotency memory for connector write methods (in-process + Redis)."""

from __future__ import annotations

import json
import threading
from typing import Any

_lock = threading.Lock()
_MEMORY: dict[str, dict[str, Any]] = {}


def _redis():
    try:
        from ..services.redis_url import redis_url
        import redis as redis_sync

        url = redis_url()
        if not url:
            return None
        client = redis_sync.Redis.from_url(
            url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True
        )
        client.ping()
        return client
    except Exception:
        return None


def recall_idempotent(key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    rk = f"connector:idem:{key}"
    client = _redis()
    if client is not None:
        try:
            raw = client.get(rk)
            if raw:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    with _lock:
        hit = _MEMORY.get(key)
        return dict(hit) if isinstance(hit, dict) else None


def store_idempotent(key: str | None, value: dict[str, Any], *, ttl_sec: int = 86400) -> None:
    if not key or not isinstance(value, dict):
        return
    rk = f"connector:idem:{key}"
    payload = dict(value)
    payload.setdefault("idempotent_replay", True)
    client = _redis()
    if client is not None:
        try:
            client.setex(rk, max(60, int(ttl_sec)), json.dumps(payload, default=str))
        except Exception:
            pass
    with _lock:
        _MEMORY[key] = payload


class ConnectorNotConfigured(RuntimeError):
    """Raised when a write method is invoked without credentials."""

    def __init__(self, tool: str, message: str | None = None):
        self.tool = tool
        msg = message or (
            f"{tool} is not connected. Add credentials in Settings → Tool Registry."
        )
        super().__init__(msg)
