"""Aggregated backend health checks (DB, Redis, optional probes)."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text as sa_text
from sqlmodel import Session

from .database import engine, _is_postgres


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sync_db_ping() -> dict[str, Any]:
    try:
        start = time.perf_counter()
        with Session(engine) as session:
            session.exec(sa_text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "message": "Database responding normally",
        }
    except Exception as exc:
        return {
            "status": "critical",
            "latency_ms": None,
            "message": str(exc),
        }


def _sync_redis_ping() -> dict[str, Any]:
    url = os.getenv("CELERY_BROKER_URL", "") or os.getenv("REDIS_URL", "")
    if not url or not url.startswith("redis"):
        return {
            "status": "warning",
            "latency_ms": None,
            "message": "Redis URL not configured (CELERY_BROKER_URL / REDIS_URL)",
        }
    try:
        import redis as redis_sync

        start = time.perf_counter()
        client = redis_sync.Redis.from_url(url, socket_connect_timeout=3, socket_timeout=3)
        client.ping()
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        client.close()
        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "message": "Redis responding normally",
        }
    except Exception as exc:
        return {
            "status": "warning",
            "latency_ms": None,
            "message": f"Redis unavailable: {exc}",
        }


def _sync_tool_accounts_probe() -> dict[str, Any]:
    """
    Placeholder for external tool credential vault checks.
    No `tool_accounts` table exists yet — report healthy with zero inventory.
    """
    return {
        "status": "healthy",
        "total": 0,
        "degraded_count": 0,
        "expiring_count": 0,
        "degraded": [],
        "expiring": [],
        "message": "No tool_accounts integration configured",
    }


def _sync_ws_probe() -> dict[str, Any]:
    """WebSocket manager not present in this API — report zero active connections."""
    return {
        "status": "healthy",
        "active_connections": 0,
        "dropped_count": 0,
        "message": "No WebSocket connection manager in this service",
    }


def _sync_slow_queries() -> dict[str, Any]:
    if not _is_postgres:
        return {
            "status": "healthy",
            "slow_query_count": 0,
            "slow_queries": [],
            "message": "pg_stat_statements not available (non-PostgreSQL database)",
        }
    try:
        with Session(engine) as session:
            result = session.execute(
                sa_text(
                    """
                    SELECT query, total_exec_time, calls, mean_exec_time
                    FROM pg_stat_statements
                    WHERE mean_exec_time > 500
                    ORDER BY mean_exec_time DESC
                    LIMIT 5
                    """
                )
            )
            rows = result.fetchall()
        slow = [
            {"query": str(r[0])[:500], "total_exec_time": float(r[1]), "calls": int(r[2])}
            for r in rows
        ]
        return {
            "status": "warning" if slow else "healthy",
            "slow_query_count": len(slow),
            "slow_queries": slow,
            "threshold_ms": 500,
        }
    except Exception:
        return {
            "status": "healthy",
            "slow_query_count": 0,
            "slow_queries": [],
            "message": "pg_stat_statements not available",
        }


def _sync_pip_audit() -> dict[str, Any]:
    req = os.path.join(os.path.dirname(__file__), "requirements.txt")
    if not os.path.isfile(req):
        return {
            "status": "healthy",
            "vulnerability_count": 0,
            "message": "requirements.txt not found for audit",
        }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--requirement", req, "--format", "json"],
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            return {
                "status": "healthy",
                "vulnerability_count": 0,
                "message": "pip-audit unavailable or failed",
            }
        data = json.loads(proc.stdout or "[]")
        vulns = len(data) if isinstance(data, list) else 0
        return {
            "status": "warning" if vulns > 0 else "healthy",
            "vulnerability_count": vulns,
            "message": f"{vulns} vulnerabilities reported by pip-audit",
        }
    except Exception as exc:
        return {
            "status": "healthy",
            "vulnerability_count": 0,
            "message": f"Dependency check unavailable: {exc}",
        }


class HealthChecker:
    async def check_all(self) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        results = await asyncio.gather(
            loop.run_in_executor(None, _sync_db_ping),
            loop.run_in_executor(None, _sync_redis_ping),
            loop.run_in_executor(None, _sync_tool_accounts_probe),
            loop.run_in_executor(None, _sync_ws_probe),
            loop.run_in_executor(None, _sync_slow_queries),
            loop.run_in_executor(None, _sync_pip_audit),
            return_exceptions=True,
        )
        normalized: list[Any] = []
        for r in results:
            if isinstance(r, BaseException):
                normalized.append(
                    {
                        "status": "warning",
                        "message": str(r),
                    }
                )
            else:
                normalized.append(r)
        return {
            "database": normalized[0],
            "redis": normalized[1],
            "tools": normalized[2],
            "websockets": normalized[3],
            "performance": normalized[4],
            "dependencies": normalized[5],
            "checked_at": _utc_iso(),
        }

    async def check_postgres(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_db_ping)

    async def check_redis(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_redis_ping)

    async def check_tool_connections(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_tool_accounts_probe)

    async def check_ws_connections(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_ws_probe)

    async def check_slow_queries(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_slow_queries)

    async def check_dependency_health(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_pip_audit)

    async def get_summary(self) -> dict[str, str]:
        full = await self.check_all()
        overall = "healthy"
        for _key, val in full.items():
            if not isinstance(val, dict):
                continue
            st = val.get("status")
            if st == "critical":
                overall = "critical"
            elif st == "warning" and overall != "critical":
                overall = "warning"
        return {
            "status": overall,
            "checked_at": _utc_iso(),
        }


health_checker = HealthChecker()
