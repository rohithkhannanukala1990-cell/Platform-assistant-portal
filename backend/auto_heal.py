"""Low-risk auto-heal actions (gated; avoids destructive Redis ops by default)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text as sa_text
from sqlmodel import Session

from .database import engine, _is_postgres


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoHealer:
    async def heal_all_low_risk(self) -> list[dict[str, Any]]:
        healed: list[dict[str, Any]] = []
        healed += await self.restart_stale_ws_sessions()
        healed += await self.clear_expired_redis_cache()
        healed += await self.postgres_vacuum_analyze()
        return healed

    async def restart_stale_ws_sessions(self) -> list[dict[str, Any]]:
        """No WebSocket manager in this service — nothing to close."""
        return []

    async def clear_expired_redis_cache(self) -> list[dict[str, Any]]:
        """
        FLUSHDB is destructive; only run when explicitly enabled.
        Prefer application-level TTL keys in future.
        """
        if os.getenv("REDIS_AUTOHEAL_ALLOW_FLUSHDB", "").lower() not in (
            "1",
            "true",
            "yes",
        ):
            return []
        url = os.getenv("CELERY_BROKER_URL", "") or os.getenv("REDIS_URL", "")
        if not url.startswith("redis"):
            return []
        try:
            import redis as redis_sync

            client = redis_sync.Redis.from_url(
                url, socket_connect_timeout=5, socket_timeout=5
            )
            client.flushdb()
            client.close()
            return [
                {
                    "action": "clear_expired_redis_cache",
                    "detail": "Redis FLUSHDB executed (REDIS_AUTOHEAL_ALLOW_FLUSHDB)",
                    "timestamp": _utc_iso(),
                }
            ]
        except Exception:
            return []

    async def postgres_vacuum_analyze(self) -> list[dict[str, Any]]:
        try:
            if _is_postgres and os.getenv("PLATFORM_AUTOHEAL_VACUUM", "").lower() in (
                "1",
                "true",
                "yes",
            ):
                with engine.connect() as conn:
                    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                    conn.execute(sa_text("VACUUM ANALYZE"))
                return [
                    {
                        "action": "postgres_vacuum_analyze",
                        "detail": "VACUUM ANALYZE completed (PostgreSQL, autocommit)",
                        "timestamp": _utc_iso(),
                    }
                ]
            with Session(engine) as session:
                session.execute(sa_text("ANALYZE"))
                session.commit()
            return [
                {
                    "action": "postgres_vacuum_analyze",
                    "detail": "ANALYZE completed (safe default; set PLATFORM_AUTOHEAL_VACUUM=true for VACUUM ANALYZE on Postgres)",
                    "timestamp": _utc_iso(),
                }
            ]
        except Exception:
            return []


auto_healer = AutoHealer()
