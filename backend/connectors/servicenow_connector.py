"""ServiceNow connector — incident create via webhook (HITL write path)."""

from __future__ import annotations

from typing import Any

import httpx

from .registry import BaseConnector


class ServiceNowConnector(BaseConnector):
    def _instance(self) -> str:
        raw = (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or ""
        ).strip().rstrip("/")
        if raw and not raw.startswith("http"):
            raw = f"https://{raw}"
        return raw

    def _webhook_url(self) -> str:
        return (
            self.account.get("webhook_url")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    def _token(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._webhook_url() or (self._instance() and self._token()))

    async def ping(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "ServiceNow webhook or instance missing"},
            }
        if self._webhook_url():
            return {"ok": True, "mode": "webhook"}
        return {"ok": True, "mode": "instance", "instance_url": self._instance()}

    async def create_incident(
        self,
        *,
        short_description: str,
        description: str = "",
        urgency: str = "2",
    ) -> dict[str, Any]:
        """Create incident via inbound webhook URL (preferred) or Table API."""
        payload = {
            "short_description": short_description,
            "description": description or short_description,
            "urgency": urgency,
            "source": "platform-assistant-portal",
        }
        webhook = self._webhook_url()
        if webhook:
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(webhook, json=payload)
                    return {
                        "ok": resp.status_code < 300,
                        "mode": "webhook",
                        "status_code": resp.status_code,
                        "body": resp.text[:300],
                    }
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:200]}

        base = self._instance()
        token = self._token()
        if not base or not token:
            return {"ok": False, "error": "not_configured"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(
                    f"{base}/api/now/table/incident",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                result = data.get("result") if isinstance(data, dict) else {}
                return {
                    "ok": resp.status_code < 300,
                    "mode": "table_api",
                    "status_code": resp.status_code,
                    "sys_id": (result or {}).get("sys_id"),
                    "number": (result or {}).get("number"),
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
            if action in ("create_incident", "create"):
                result = await self.create_incident(
                    short_description=str(params.get("short_description") or params.get("title") or ""),
                    description=str(params.get("description") or ""),
                    urgency=str(params.get("urgency") or "2"),
                )
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "servicenow", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
