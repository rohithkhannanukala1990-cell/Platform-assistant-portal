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


# TODO: Provide health/scorecard summary data that can be consumed by golden path applicability logic and AI grounding
def get_entity_health_summary(
    session: Session,
    entity: Any,
    *,
    standards: list[Any] | None = None,
    scorecards: list[Any] | None = None,
) -> dict[str, Any]:
    """Return a compact, deterministic entity health summary and gap signals."""
    from .routers.standards import (
        calculate_service_health_status,
        collect_service_scorecards,
        evaluate_service_standards,
    )

    if standards is None:
        standards = evaluate_service_standards(session, entity)
    if scorecards is None:
        scorecards = collect_service_scorecards(session, entity)
    gaps: set[str] = set()

    for standard in standards:
        if standard.status != "pass":
            gaps.add("production_readiness")

    for scorecard in scorecards:
        grade = (scorecard.grade or "").lower()
        ratio = (
            scorecard.score / scorecard.max_score
            if scorecard.max_score > 0
            else 0
        )
        if grade in {"warn", "fail"} or ratio < 0.8:
            name = scorecard.name.lower()
            if any(term in name for term in ("health", "reliability", "observ")):
                gaps.add("observability")
            if any(term in name for term in ("repo", "pipeline", "build", "deploy")):
                gaps.add("cicd")
            if any(term in name for term in ("security", "language")):
                gaps.add("security")
            if any(term in name for term in ("owner", "description", "tag")):
                gaps.add("catalog_metadata")

    health_status = (getattr(entity, "health_status", None) or "unknown").lower()
    if health_status in {"unknown", "degraded", "unhealthy", "critical"}:
        gaps.add("observability")
    if not (getattr(entity, "repo_url", None) or "").strip():
        gaps.add("cicd")

    overall_status = calculate_service_health_status(standards, scorecards)
    return {
        "entity_id": str(entity.id),
        "overall_status": overall_status,
        "standards": [row.model_dump() for row in standards],
        "scorecards": [row.model_dump() for row in scorecards],
        "gaps": sorted(gaps),
    }


# TODO: Provide health/scorecard summary data that can be consumed by golden path applicability logic and AI grounding
# TODO: Extend tool_accounts probe to check per-connector health (GitHub, Jira, AWS, Kubernetes, PagerDuty) and summarize statuses
def _timed_probe(probe_name: str, fn) -> dict[str, Any]:
    from .observability.metrics import HEALTH_PROBE_DURATION_SECONDS

    start = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        result = {
            "status": "warning",
            "latency_ms": None,
            "message": str(exc),
        }
    duration = time.perf_counter() - start
    try:
        HEALTH_PROBE_DURATION_SECONDS.labels(probe_name=probe_name).observe(duration)
    except Exception:
        pass
    if isinstance(result, dict) and result.get("latency_ms") is None:
        result = {**result, "latency_ms": round(duration * 1000, 2)}
    return result


def _async_probe_result(coro) -> dict[str, Any]:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Already inside an event loop (rare for executor workers).
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# TODO: Use GitHubConnector to perform a simple API call and report status/latency
def _sync_github_probe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        if not os.getenv("GITHUB_TOKEN", "").strip():
            return {
                "status": "healthy",
                "message": "GITHUB_TOKEN not configured",
                "configured": False,
            }

        async def _check() -> dict[str, Any]:
            from .connectors.github_connector import GitHubConnector

            connector = GitHubConnector({"tool_id": "github"})
            start = time.perf_counter()
            result = await connector.execute_action("test_connection", {})
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if result.get("ok"):
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "configured": True,
                    "message": "GitHub API reachable",
                }
            error = result.get("error") or {}
            return {
                "status": "critical" if error.get("type") == "auth_failed" else "warning",
                "latency_ms": latency_ms,
                "configured": True,
                "message": error.get("message") or "GitHub probe failed",
                "error": error,
            }

        return _async_probe_result(_check())

    return _timed_probe("github", _run)


# TODO: Implement similar reachability checks for Jira connector
def _sync_jira_probe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        url = os.getenv("JIRA_URL", "").strip() or os.getenv("JIRA_DOMAIN", "").strip()
        email = os.getenv("JIRA_EMAIL", "").strip()
        token = os.getenv("JIRA_API_TOKEN", "").strip()
        if not url or not email or not token:
            return {
                "status": "healthy",
                "message": "Jira credentials not configured",
                "configured": False,
            }
        if not url.startswith("http"):
            url = f"https://{url}"
        try:
            import httpx

            start = time.perf_counter()
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    f"{url.rstrip('/')}/rest/api/2/myself",
                    auth=(email, token),
                )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code < 400:
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "configured": True,
                    "message": "Jira API reachable",
                }
            status = "critical" if resp.status_code in (401, 403) else "warning"
            return {
                "status": status,
                "latency_ms": latency_ms,
                "configured": True,
                "message": f"Jira HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "message": f"Jira unreachable: {exc}",
            }

    return _timed_probe("jira", _run)


def _sync_aws_probe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        if not (
            os.getenv("AWS_ACCESS_KEY_ID", "").strip()
            or os.getenv("AWS_PROFILE", "").strip()
            or os.getenv("AWS_REGION", "").strip()
        ):
            return {
                "status": "healthy",
                "message": "AWS credentials not configured",
                "configured": False,
            }
        try:
            import boto3

            start = time.perf_counter()
            sts = boto3.client("sts", region_name=os.getenv("AWS_REGION", "us-east-1"))
            identity = sts.get_caller_identity()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "configured": True,
                "message": f"AWS identity {identity.get('Account', 'unknown')}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "message": f"AWS unreachable: {exc}",
            }

    return _timed_probe("aws", _run)


def _sync_kubernetes_probe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        kubeconfig = os.getenv("KUBECONFIG", "").strip()
        in_cluster = os.path.exists(
            "/var/run/secrets/kubernetes.io/serviceaccount/token"
        )
        if not kubeconfig and not in_cluster:
            return {
                "status": "healthy",
                "message": "Kubernetes config not available",
                "configured": False,
            }
        try:
            from kubernetes import client, config

            start = time.perf_counter()
            if in_cluster:
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=kubeconfig or None)
            version = client.VersionApi().get_code()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "configured": True,
                "message": f"Kubernetes API {getattr(version, 'git_version', 'ok')}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "message": f"Kubernetes unreachable: {exc}",
            }

    return _timed_probe("kubernetes", _run)


def _sync_pagerduty_probe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        key = os.getenv("PAGERDUTY_API_KEY", "").strip()
        if not key:
            return {
                "status": "healthy",
                "message": "PAGERDUTY_API_KEY not configured",
                "configured": False,
            }
        try:
            import httpx

            start = time.perf_counter()
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(
                    "https://api.pagerduty.com/abilities",
                    headers={
                        "Authorization": f"Token token={key}",
                        "Accept": "application/vnd.pagerduty+json;version=2",
                    },
                )
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if resp.status_code < 400:
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "configured": True,
                    "message": "PagerDuty API reachable",
                }
            status = "critical" if resp.status_code in (401, 403) else "warning"
            return {
                "status": status,
                "latency_ms": latency_ms,
                "configured": True,
                "message": f"PagerDuty HTTP {resp.status_code}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "message": f"PagerDuty unreachable: {exc}",
            }

    return _timed_probe("pagerduty", _run)


def _sync_tool_accounts_probe() -> dict[str, Any]:
    """Aggregate per-connector reachability into a tools health summary."""
    connectors = {
        "github": _sync_github_probe(),
        "jira": _sync_jira_probe(),
        "aws": _sync_aws_probe(),
        "kubernetes": _sync_kubernetes_probe(),
        "pagerduty": _sync_pagerduty_probe(),
    }
    degraded = [
        name
        for name, row in connectors.items()
        if row.get("configured") is True
        and row.get("status") in {"warning", "critical"}
    ]
    configured = [
        name for name, row in connectors.items() if row.get("configured") is True
    ]
    configured_rows = [
        row for row in connectors.values() if row.get("configured") is True
    ]
    statuses = [row.get("status") for row in configured_rows]
    if any(status == "critical" for status in statuses):
        overall = "critical"
    elif degraded:
        overall = "warning"
    else:
        overall = "healthy"
    return {
        "status": overall,
        "total": len(connectors),
        "configured_count": len(configured),
        "degraded_count": len(degraded),
        "expiring_count": 0,
        "degraded": degraded,
        "expiring": [],
        "connectors": connectors,
        "message": (
            "All connectors healthy"
            if overall == "healthy"
            else f"{len(degraded)} connector(s) degraded"
        ),
    }


def _sync_ws_probe() -> dict[str, Any]:
    """WebSocket manager not present in this API — report zero active connections."""
    return _timed_probe(
        "websockets",
        lambda: {
            "status": "healthy",
            "active_connections": 0,
            "dropped_count": 0,
            "message": "No WebSocket connection manager in this service",
        },
    )


def _sync_db_ping_timed() -> dict[str, Any]:
    return _timed_probe("database", _sync_db_ping)


def _sync_redis_ping_timed() -> dict[str, Any]:
    return _timed_probe("redis", _sync_redis_ping)


def _sync_slow_queries() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
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
                {
                    "query": str(r[0])[:500],
                    "total_exec_time": float(r[1]),
                    "calls": int(r[2]),
                }
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

    return _timed_probe("performance", _run)


def _sync_pip_audit() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        req = os.path.join(os.path.dirname(__file__), "requirements.txt")
        if not os.path.isfile(req):
            return {
                "status": "healthy",
                "vulnerability_count": 0,
                "message": "requirements.txt not found for audit",
            }
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "--requirement",
                    req,
                    "--format",
                    "json",
                ],
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

    return _timed_probe("dependencies", _run)


class HealthChecker:
    async def check_all(self) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        results = await asyncio.gather(
            loop.run_in_executor(None, _sync_db_ping_timed),
            loop.run_in_executor(None, _sync_redis_ping_timed),
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
        tools = normalized[2] if isinstance(normalized[2], dict) else {}
        return {
            "database": normalized[0],
            "redis": normalized[1],
            "tools": tools,
            "connectors": tools.get("connectors", {}),
            "websockets": normalized[3],
            "performance": normalized[4],
            "dependencies": normalized[5],
            "checked_at": _utc_iso(),
        }

    async def check_postgres(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, _sync_db_ping_timed
        )

    async def check_redis(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, _sync_redis_ping_timed
        )

    async def check_tool_connections(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, _sync_tool_accounts_probe
        )

    async def check_ws_connections(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(None, _sync_ws_probe)

    async def check_slow_queries(self) -> dict[str, Any]:
        return await asyncio.get_running_loop().run_in_executor(
            None, _sync_slow_queries
        )

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
            # Nested connector map has no top-level status; inspect children.
            if _key == "connectors":
                for connector in val.values():
                    if not isinstance(connector, dict):
                        continue
                    cst = connector.get("status")
                    if cst == "critical":
                        overall = "critical"
                    elif cst == "warning" and overall != "critical":
                        overall = "warning"
        return {
            "status": overall,
            "checked_at": _utc_iso(),
        }


health_checker = HealthChecker()
