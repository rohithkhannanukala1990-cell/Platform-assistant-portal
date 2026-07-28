"""Prometheus connector — read-only query + alerts."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from .registry import BaseConnector


class PrometheusConnector(BaseConnector):
    def _base_url(self) -> str:
        return (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or ""
        ).rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @property
    def configured(self) -> bool:
        return bool(self._base_url())

    async def ping(self) -> dict[str, Any]:
        base = self._base_url()
        if not base:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "Prometheus instance_url missing"},
            }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(urljoin(base + "/", "-/ready"), headers=self._headers())
                if resp.status_code >= 400:
                    # Some installs expose /api/v1/status/buildinfo instead
                    resp = await client.get(
                        urljoin(base + "/", "api/v1/status/buildinfo"),
                        headers=self._headers(),
                    )
                if resp.status_code in (401, 403):
                    return {"ok": False, "error": {"type": "auth_failed", "message": f"HTTP {resp.status_code}"}}
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "error": {"type": "network_error", "message": f"HTTP {resp.status_code}"},
                    }
                return {"ok": True, "instance_url": base}
        except Exception as exc:
            return {"ok": False, "error": {"type": "network_error", "message": str(exc)[:200]}}

    async def query(self, promql: str) -> dict[str, Any]:
        base = self._base_url()
        if not base or not (promql or "").strip():
            return {"status": "error", "data": {"result": []}}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    urljoin(base + "/", "api/v1/query"),
                    headers=self._headers(),
                    params={"query": promql},
                )
                if resp.status_code >= 400:
                    return {"status": "error", "http_status": resp.status_code, "data": {"result": []}}
                data = resp.json()
                return data if isinstance(data, dict) else {"status": "error", "data": {"result": []}}
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200], "data": {"result": []}}

    async def list_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        base = self._base_url()
        if not base:
            return []
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.get(
                    urljoin(base + "/", "api/v1/alerts"),
                    headers=self._headers(),
                )
                if resp.status_code >= 400:
                    return []
                data = resp.json()
                alerts = (data.get("data") or {}).get("alerts") if isinstance(data, dict) else []
                out = []
                for a in alerts or []:
                    labels = a.get("labels") or {}
                    annotations = a.get("annotations") or {}
                    out.append(
                        {
                            "state": a.get("state"),
                            "name": labels.get("alertname"),
                            "severity": labels.get("severity"),
                            "service": labels.get("service") or labels.get("job"),
                            "summary": annotations.get("summary") or annotations.get("description"),
                            "active_at": a.get("activeAt"),
                            "labels": labels,
                        }
                    )
                return out[:limit]
        except Exception:
            return []

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "prometheus", "action": action, "result": result}
            if action == "query":
                result = await self.query(str(params.get("query") or params.get("promql") or ""))
                return {"ok": result.get("status") == "success", "tool": "prometheus", "action": action, "result": result}
            if action == "list_alerts":
                result = await self.list_alerts(limit=int(params.get("limit", 50)))
                return {"ok": True, "tool": "prometheus", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "prometheus", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
