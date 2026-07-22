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


# TODO(S3-P3.1): Add connector-specific health probes (GitHub, Jira, AWS, Kubernetes, PagerDuty) using tool_accounts
_PROBE_HTTP_TIMEOUT = 3.0  # Keep health routes snappy; avoid heavy-blocking calls.


def _timed_probe(probe_name: str, fn) -> dict[str, Any]:
    from .observability.metrics import observe_health_probe

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
    # TODO(S3-P3.1): Increment health and connector metrics during probe runs and errors
    observe_health_probe(probe_name, duration)
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


def _tool_id_of(account: Any) -> str:
    if isinstance(account, dict):
        return str(account.get("tool_id") or "").strip().lower()
    return str(getattr(account, "tool_id", None) or "").strip().lower()


def _account_as_dict(account: Any) -> dict[str, Any]:
    if isinstance(account, dict):
        data = dict(account)
    else:
        data = {
            "id": getattr(account, "id", None),
            "tool_id": getattr(account, "tool_id", None),
            "account_name": getattr(account, "account_name", None),
            "account_identifier": getattr(account, "account_identifier", None),
            "instance_url": getattr(account, "instance_url", None),
            "environment": getattr(account, "environment", None),
            "region": getattr(account, "region", None),
            "auth_type": getattr(account, "auth_type", None),
            "credentials_vault_ref": getattr(account, "credentials_vault_ref", None),
            "status": getattr(account, "status", None),
            "tenant_id": getattr(account, "tenant_id", None),
        }
    ref = (data.get("credentials_vault_ref") or data.get("token") or "").strip()
    if ref:
        data.setdefault("token", ref)
        data.setdefault("api_token", ref)
        data.setdefault("api_key", ref)
    return data


def _accounts_for(tool_accounts: list | None, tool_id: str) -> list[dict[str, Any]]:
    return [
        _account_as_dict(a)
        for a in (tool_accounts or [])
        if _tool_id_of(a) == tool_id.lower()
    ]


def _pick_account(accounts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Prefer a connected account with credentials; otherwise first row."""
    if not accounts:
        return None
    with_creds = [
        a
        for a in accounts
        if (a.get("credentials_vault_ref") or a.get("token") or a.get("api_token") or "").strip()
    ]
    pool = with_creds or accounts
    connected = [a for a in pool if (a.get("status") or "").lower() == "connected"]
    return (connected or pool)[0]


def _load_active_tool_accounts() -> list[dict[str, Any]]:
    try:
        from sqlmodel import select

        from .database import ToolAccount

        with Session(engine) as session:
            rows = session.exec(
                select(ToolAccount).where(ToolAccount.is_active == 1)
            ).all()
            return [_account_as_dict(r) for r in rows]
    except Exception:
        return []


def _record_probe_error(connector: str, result: dict[str, Any]) -> None:
    if result.get("configured") is False:
        return
    if result.get("status") not in {"warning", "critical"}:
        return
    from .observability.metrics import record_connector_error

    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    error_type = (
        (error or {}).get("type")
        or ("auth_failed" if result.get("status") == "critical" else "probe_failed")
    )
    record_connector_error(connector, str(error_type))


def _log_probe_result(connector: str, result: dict[str, Any]) -> None:
    try:
        from .observability.logger import get_request_context, logger

        ctx = get_request_context()
        logger.info(
            "Health probe completed",
            extra={
                "connector": connector,
                "probe_name": connector,
                "request_id": ctx.get("request_id"),
                "workspace_id": ctx.get("workspace_id"),
                "status": result.get("status"),
                "latency_ms": result.get("latency_ms"),
                "error_type": (result.get("error") or {}).get("type")
                if isinstance(result.get("error"), dict)
                else None,
            },
        )
    except Exception:
        pass


def _finalize_connector_probe(
    connector: str,
    result: dict[str, Any],
    *,
    record_errors: bool = True,
) -> dict[str, Any]:
    if record_errors:
        _record_probe_error(connector, result)
    _log_probe_result(connector, result)
    return result


def _sync_github_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        accounts = _accounts_for(tool_accounts, "github")
        picked = _pick_account(accounts)
        env_token = os.getenv("GITHUB_TOKEN", "").strip()
        if not picked and not env_token:
            return {
                "status": "healthy",
                "latency_ms": None,
                "message": "GitHub not configured (no tool account or GITHUB_TOKEN)",
                "configured": False,
                "accounts": 0,
            }

        account = picked or {"tool_id": "github"}
        if env_token and not (account.get("token") or "").strip():
            account = {**account, "token": env_token, "tool_id": "github"}

        async def _check() -> dict[str, Any]:
            from .connectors.github_connector import GitHubConnector

            connector = GitHubConnector(account)
            start = time.perf_counter()
            result = await connector.execute_action("ping", {})
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            if result.get("ok"):
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "configured": True,
                    "accounts": len(accounts),
                    "account_name": account.get("account_name"),
                    "message": "GitHub API reachable",
                }
            error = result.get("error") or {}
            return {
                "status": "critical" if error.get("type") == "auth_failed" else "warning",
                "latency_ms": latency_ms,
                "configured": True,
                "accounts": len(accounts),
                "account_name": account.get("account_name"),
                "message": error.get("message") or "GitHub probe failed",
                "error": error,
            }

        return _async_probe_result(_check())

    # GitHubConnector already increments CONNECTOR_ERRORS_TOTAL on failure.
    return _finalize_connector_probe(
        "github", _timed_probe("github", _run), record_errors=False
    )


def _sync_jira_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        accounts = _accounts_for(tool_accounts, "jira")
        picked = _pick_account(accounts)
        url = (
            ((picked or {}).get("instance_url") or "").strip()
            or os.getenv("JIRA_URL", "").strip()
            or os.getenv("JIRA_DOMAIN", "").strip()
        )
        email = (
            ((picked or {}).get("account_identifier") or "").strip()
            or os.getenv("JIRA_EMAIL", "").strip()
        )
        token = (
            ((picked or {}).get("api_token") or (picked or {}).get("token") or "").strip()
            or os.getenv("JIRA_API_TOKEN", "").strip()
        )
        if not url or not email or not token:
            return {
                "status": "healthy",
                "latency_ms": None,
                "message": "Jira credentials not configured",
                "configured": False,
                "accounts": len(accounts),
            }
        if not url.startswith("http"):
            url = f"https://{url}"
        try:
            import httpx

            start = time.perf_counter()
            with httpx.Client(timeout=_PROBE_HTTP_TIMEOUT) as client:
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
                    "accounts": len(accounts),
                    "account_name": (picked or {}).get("account_name"),
                    "message": "Jira API reachable",
                }
            status = "critical" if resp.status_code in (401, 403) else "warning"
            return {
                "status": status,
                "latency_ms": latency_ms,
                "configured": True,
                "accounts": len(accounts),
                "message": f"Jira HTTP {resp.status_code}",
                "error": {
                    "type": "auth_failed" if status == "critical" else "probe_failed",
                    "message": f"HTTP {resp.status_code}",
                },
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "accounts": len(accounts),
                "message": f"Jira unreachable: {exc}",
                "error": {"type": "network_error", "message": str(exc)},
            }

    return _finalize_connector_probe("jira", _timed_probe("jira", _run))


def _sync_aws_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        accounts = _accounts_for(tool_accounts, "aws")
        picked = _pick_account(accounts)
        region = (
            ((picked or {}).get("region") or "").strip()
            or os.getenv("AWS_REGION", "").strip()
            or "us-east-1"
        )
        has_env = bool(
            os.getenv("AWS_ACCESS_KEY_ID", "").strip()
            or os.getenv("AWS_PROFILE", "").strip()
            or os.getenv("AWS_REGION", "").strip()
        )
        if not picked and not has_env:
            return {
                "status": "healthy",
                "latency_ms": None,
                "message": "AWS credentials not configured",
                "configured": False,
                "accounts": len(accounts),
            }
        try:
            import boto3

            start = time.perf_counter()
            sts = boto3.client("sts", region_name=region)
            identity = sts.get_caller_identity()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "configured": True,
                "accounts": len(accounts),
                "account_name": (picked or {}).get("account_name"),
                "message": f"AWS identity {identity.get('Account', 'unknown')}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "accounts": len(accounts),
                "message": f"AWS unreachable: {exc}",
                "error": {"type": "network_error", "message": str(exc)},
            }

    return _finalize_connector_probe("aws", _timed_probe("aws", _run))


def _sync_kubernetes_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        accounts = _accounts_for(tool_accounts, "kubernetes")
        picked = _pick_account(accounts)
        kubeconfig = (
            ((picked or {}).get("credentials_vault_ref") or "").strip()
            or os.getenv("KUBECONFIG", "").strip()
        )
        in_cluster = os.path.exists(
            "/var/run/secrets/kubernetes.io/serviceaccount/token"
        )
        if not picked and not kubeconfig and not in_cluster:
            return {
                "status": "healthy",
                "latency_ms": None,
                "message": "Kubernetes config not available",
                "configured": False,
                "accounts": len(accounts),
            }
        try:
            from kubernetes import client, config

            start = time.perf_counter()
            if in_cluster and not kubeconfig:
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=kubeconfig or None)
            version = client.VersionApi().get_code()
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "configured": True,
                "accounts": len(accounts),
                "account_name": (picked or {}).get("account_name"),
                "message": f"Kubernetes API {getattr(version, 'git_version', 'ok')}",
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "accounts": len(accounts),
                "message": f"Kubernetes unreachable: {exc}",
                "error": {"type": "network_error", "message": str(exc)},
            }

    return _finalize_connector_probe("kubernetes", _timed_probe("kubernetes", _run))


def _sync_pagerduty_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        accounts = _accounts_for(tool_accounts, "pagerduty")
        picked = _pick_account(accounts)
        key = (
            ((picked or {}).get("api_key") or (picked or {}).get("token") or "").strip()
            or os.getenv("PAGERDUTY_API_KEY", "").strip()
        )
        if not key:
            return {
                "status": "healthy",
                "latency_ms": None,
                "message": "PagerDuty API key not configured",
                "configured": False,
                "accounts": len(accounts),
            }
        try:
            import httpx

            start = time.perf_counter()
            with httpx.Client(timeout=_PROBE_HTTP_TIMEOUT) as client:
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
                    "accounts": len(accounts),
                    "account_name": (picked or {}).get("account_name"),
                    "message": "PagerDuty API reachable",
                }
            status = "critical" if resp.status_code in (401, 403) else "warning"
            return {
                "status": status,
                "latency_ms": latency_ms,
                "configured": True,
                "accounts": len(accounts),
                "message": f"PagerDuty HTTP {resp.status_code}",
                "error": {
                    "type": "auth_failed" if status == "critical" else "probe_failed",
                    "message": f"HTTP {resp.status_code}",
                },
            }
        except Exception as exc:
            return {
                "status": "warning",
                "configured": True,
                "accounts": len(accounts),
                "message": f"PagerDuty unreachable: {exc}",
                "error": {"type": "network_error", "message": str(exc)},
            }

    return _finalize_connector_probe("pagerduty", _timed_probe("pagerduty", _run))


def _sync_tool_accounts_probe(tool_accounts: list | None = None) -> dict[str, Any]:
    """Aggregate per-connector reachability into a tools health summary."""
    accounts = (
        list(tool_accounts)
        if tool_accounts is not None
        else _load_active_tool_accounts()
    )
    # Run connector probes in parallel to keep /health/full responsive.
    from concurrent.futures import ThreadPoolExecutor, as_completed

    probes = {
        "github": (_sync_github_probe, accounts),
        "jira": (_sync_jira_probe, accounts),
        "aws": (_sync_aws_probe, accounts),
        "kubernetes": (_sync_kubernetes_probe, accounts),
        "pagerduty": (_sync_pagerduty_probe, accounts),
    }
    connectors: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(fn, accs): name for name, (fn, accs) in probes.items()
        }
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                connectors[name] = fut.result()
            except Exception as exc:
                connectors[name] = {
                    "status": "warning",
                    "latency_ms": None,
                    "configured": False,
                    "message": str(exc),
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
        "tool_account_count": len(accounts),
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
