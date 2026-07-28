"""Generic outbound HTTP webhook — post portal events to a customer URL."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from .registry import BaseConnector


class OutboundWebhookConnector(BaseConnector):
    """Delivers signed-ish JSON event payloads to a customer webhook URL."""

    def _url(self) -> str:
        return (
            self.account.get("webhook_url")
            or self.account.get("instance_url")
            or self.account.get("url")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    def _secret(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("signing_secret")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._url()) and self._url().startswith("http")

    async def ping(self) -> dict[str, Any]:
        url = self._url()
        if not self.configured:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "Outbound webhook URL missing"},
            }
        # Soft ping — do not POST on ping; just validate URL shape.
        return {"ok": True, "url_host": url.split("/")[2] if "://" in url else url[:40]}

    async def deliver(self, event: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = self._url()
        if not self.configured:
            return {"ok": False, "error": "not_configured"}
        body = {
            "event": event or "custom",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {},
            "source": "platform-assistant-portal",
        }
        headers = {"Content-Type": "application/json", "User-Agent": "PlatformAssistantPortal/1.0"}
        secret = self._secret()
        if secret:
            headers["X-Portal-Webhook-Secret"] = secret
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=body, headers=headers)
                return {
                    "ok": resp.status_code < 300,
                    "status_code": resp.status_code,
                    "event": event,
                    "body": resp.text[:300],
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "event": event}

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {
                    "ok": bool(result.get("ok")),
                    "tool": "outbound_webhook",
                    "action": action,
                    "result": result,
                }
            if action in ("deliver", "notify", "post"):
                result = await self.deliver(
                    str(params.get("event") or "custom"),
                    params.get("payload") if isinstance(params.get("payload"), dict) else {},
                )
                return {
                    "ok": bool(result.get("ok")),
                    "tool": "outbound_webhook",
                    "action": action,
                    "result": result,
                }
        except Exception as exc:
            return {"ok": False, "tool": "outbound_webhook", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
