"""Readiness probes for HA / pilot (Phase G7).

``/health/ready`` must verify database + Redis (broker). Redis is required when
a Redis URL is configured or when ``ENV=production``; otherwise Redis may be
skipped for local/pytest SQLite stacks.
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import text as sa_text
from sqlmodel import Session


def _env_name() -> str:
    return (os.getenv("ENV") or "dev").strip().lower()


def is_production_env() -> bool:
    return _env_name() in {"production", "prod"}


def redis_url() -> str:
    return (os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL") or "").strip()


def uses_sqlite(database_url: str | None = None) -> bool:
    url = (database_url if database_url is not None else os.getenv("DATABASE_URL") or "").strip().lower()
    return url.startswith("sqlite:")


def demo_data_flag() -> bool | None:
    """Explicit ENABLE_DEMO_DATA flag, or None if unset."""
    raw = (os.getenv("ENABLE_DEMO_DATA") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def workspace_isolation_enforced() -> bool:
    flag = (os.getenv("ENFORCE_WORKSPACE_ISOLATION") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def production_safety_snapshot() -> dict[str, Any]:
    """Config flags expected for the HA / pilot path (compose prod defaults)."""
    demo = demo_data_flag()
    return {
        "env": _env_name(),
        "enable_demo_data": demo,
        "enforce_workspace_isolation": workspace_isolation_enforced(),
        "uses_sqlite": uses_sqlite(),
        "redis_configured": bool(redis_url().startswith("redis")),
        "ok_for_pilot": (
            is_production_env()
            and demo is False
            and workspace_isolation_enforced()
            and not uses_sqlite()
            and bool(redis_url().startswith("redis"))
        ),
    }


def check_database() -> dict[str, Any]:
    from ..database import engine

    try:
        with Session(engine) as session:
            session.exec(sa_text("SELECT 1"))
        return {"status": "ok", "detail": "database_reachable"}
    except Exception as exc:
        return {
            "status": "error",
            "detail": "database_unavailable",
            "error": str(exc)[:200],
        }


def check_redis(*, required: bool | None = None) -> dict[str, Any]:
    """Ping Redis.

    Required by default when ``ENV=production``, or when a Redis URL is set on a
    non-SQLite stack. Local/pytest SQLite stacks treat Redis as optional so a
    leftover ``CELERY_BROKER_URL`` in ``.env`` does not fail readiness.
    """
    url = redis_url()
    env = _env_name()
    if required is not None:
        must = required
    elif is_production_env():
        must = True
    elif uses_sqlite() and env in {"test", "dev", "development"}:
        must = False
    else:
        must = bool(url.startswith("redis"))

    if not url or not url.startswith("redis"):
        if must:
            return {
                "status": "error",
                "detail": "redis_not_configured",
                "required": True,
            }
        return {
            "status": "skipped",
            "detail": "redis_not_configured",
            "required": False,
        }

    try:
        from ..health import _sync_redis_ping

        probe = _sync_redis_ping()
        status = (probe.get("status") or "").lower()
        if status == "healthy":
            return {
                "status": "ok",
                "detail": "redis_reachable",
                "latency_ms": probe.get("latency_ms"),
                "required": must,
            }
        if not must:
            return {
                "status": "skipped",
                "detail": "redis_unreachable_optional",
                "message": probe.get("message"),
                "required": False,
            }
        return {
            "status": "error",
            "detail": "redis_unavailable",
            "message": probe.get("message"),
            "required": True,
        }
    except Exception as exc:
        if not must:
            return {
                "status": "skipped",
                "detail": "redis_unreachable_optional",
                "error": str(exc)[:200],
                "required": False,
            }
        return {
            "status": "error",
            "detail": "redis_unavailable",
            "error": str(exc)[:200],
            "required": True,
        }


def evaluate_readiness(*, require_redis: bool | None = None) -> dict[str, Any]:
    """Return a readiness payload. ``ready`` is True only when required checks pass."""
    db = check_database()
    redis = check_redis(required=require_redis)
    db_ok = db.get("status") == "ok"
    redis_ok = redis.get("status") in {"ok", "skipped"}
    ready = db_ok and redis_ok
    return {
        "status": "ready" if ready else "not_ready",
        "service": "platform-assistant-portal",
        "checks": {
            "database": db,
            "redis": redis,
        },
    }
