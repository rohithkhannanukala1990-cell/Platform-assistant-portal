"""ArgoCD connector — read-only application health."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from .registry import BaseConnector


class ArgoCDConnector(BaseConnector):
    def _base_url(self) -> str:
        return (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or ""
        ).rstrip("/")

    def _token(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    def _verify_tls(self) -> bool:
        """TLS verify on by default. Opt-in insecure only via account flag; never in production ENV."""
        import os

        env = (os.getenv("ENV") or "dev").strip().lower()
        if env in {"production", "prod", "dr"}:
            return True
        raw = str(self.account.get("insecure_skip_tls_verify") or "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return False
        return True

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @property
    def configured(self) -> bool:
        return bool(self._base_url() and self._token())

    async def ping(self) -> dict[str, Any]:
        base = self._base_url()
        if not self.configured:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "ArgoCD instance_url or token missing"},
            }
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=self._verify_tls()) as client:
                resp = await client.get(
                    urljoin(base + "/", "api/v1/session/userinfo"),
                    headers=self._headers(),
                )
                if resp.status_code in (401, 403):
                    return {"ok": False, "error": {"type": "auth_failed", "message": f"HTTP {resp.status_code}"}}
                if resp.status_code >= 400:
                    # Fallback: list apps endpoint
                    resp = await client.get(
                        urljoin(base + "/", "api/v1/applications"),
                        headers=self._headers(),
                        params={"fields": "metadata.name"},
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

    async def list_applications(self, limit: int = 50) -> list[dict[str, Any]]:
        base = self._base_url()
        if not self.configured:
            return []
        try:
            async with httpx.AsyncClient(timeout=25.0, verify=self._verify_tls()) as client:
                resp = await client.get(
                    urljoin(base + "/", "api/v1/applications"),
                    headers=self._headers(),
                )
                if resp.status_code >= 400:
                    return []
                data = resp.json()
                items = data.get("items") if isinstance(data, dict) else []
                out = []
                for app in items or []:
                    meta = app.get("metadata") or {}
                    status = app.get("status") or {}
                    health = (status.get("health") or {}).get("status")
                    sync = (status.get("sync") or {}).get("status")
                    out.append(
                        {
                            "name": meta.get("name"),
                            "namespace": meta.get("namespace"),
                            "project": (app.get("spec") or {}).get("project"),
                            "health": health,
                            "sync": sync,
                            "revision": ((status.get("sync") or {}).get("revision")),
                        }
                    )
                return out[:limit]
        except Exception:
            return []

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "argocd", "action": action, "result": result}
            if action in ("list_applications", "list_apps"):
                result = await self.list_applications(limit=int(params.get("limit", 50)))
                return {"ok": True, "tool": "argocd", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "argocd", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
