"""ServiceNow connector — incident + change request writes (HITL path)."""

from __future__ import annotations

from typing import Any

import httpx

from ..services.ssrf import assert_safe_outbound_url
from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
from .registry import BaseConnector

# Human name → ServiceNow change_request state values
CHANGE_STATES = {
    "assess": "-4",
    "authorize": "-3",
    "scheduled": "-2",
    "implement": "-1",
    "review": "0",
    "closed": "3",
    "new": "-5",
    "draft": "1",
}


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
            or ""
        ).strip()

    def _token(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._webhook_url() or (self._instance() and self._token()))

    def _require_configured(self) -> None:
        if not self.configured:
            raise ConnectorNotConfigured("ServiceNow")

    def _record_url(self, table: str, sys_id: str) -> str:
        base = self._instance()
        if not base or not sys_id:
            return ""
        return f"{base}/nav_to.do?uri={table}.do?sys_id={sys_id}"

    async def ping(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "ok": False,
                "error": {"type": "not_configured", "message": "ServiceNow webhook or instance missing"},
            }
        if self._webhook_url():
            return {"ok": True, "mode": "webhook"}
        return {"ok": True, "mode": "instance", "instance_url": self._instance()}

    async def _table_post(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_configured()
        webhook = self._webhook_url()
        if webhook and table == "incident":
            assert_safe_outbound_url(webhook)
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(webhook, json=payload)
                return {
                    "ok": resp.status_code < 300,
                    "mode": "webhook",
                    "status_code": resp.status_code,
                    "body": resp.text[:300],
                    "url": webhook,
                }
        base = self._instance()
        token = self._token()
        if not base or not token:
            raise ConnectorNotConfigured("ServiceNow")
        url = f"{base}/api/now/table/{table}"
        assert_safe_outbound_url(url)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
            )
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            result = data.get("result") if isinstance(data, dict) else {}
            sys_id = (result or {}).get("sys_id") or ""
            return {
                "ok": resp.status_code < 300,
                "mode": "table_api",
                "status_code": resp.status_code,
                "sys_id": sys_id,
                "number": (result or {}).get("number"),
                "url": self._record_url(table, sys_id),
                "result": result,
            }

    async def _table_patch(self, table: str, sys_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_configured()
        base = self._instance()
        token = self._token()
        if not base or not token:
            raise ConnectorNotConfigured("ServiceNow")
        url = f"{base}/api/now/table/{table}/{sys_id}"
        assert_safe_outbound_url(url)
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.patch(
                url,
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
                "status_code": resp.status_code,
                "sys_id": sys_id,
                "url": self._record_url(table, sys_id),
                "result": result,
            }

    async def create_incident(
        self,
        short_description: str,
        description: str = "",
        urgency: str = "3",
        impact: str = "3",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        payload = {
            "short_description": short_description,
            "description": description or short_description,
            "urgency": str(urgency or "3"),
            "impact": str(impact or "3"),
            "source": "platform-assistant-portal",
        }
        result = await self._table_post("incident", payload)
        if result.get("ok"):
            store_idempotent(idempotency_key, {**result, "reused": False})
        return result

    async def create_change_request(
        self,
        short_description: str,
        description: str,
        risk: str = "moderate",
        planned_start: str | None = None,
        planned_end: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        payload: dict[str, Any] = {
            "short_description": short_description,
            "description": description or short_description,
            "risk": risk or "moderate",
            "type": "normal",
        }
        if planned_start:
            payload["start_date"] = planned_start
        if planned_end:
            payload["end_date"] = planned_end
        result = await self._table_post("change_request", payload)
        if result.get("ok"):
            store_idempotent(idempotency_key, {**result, "reused": False})
        return result

    async def update_change_state(
        self,
        sys_id: str,
        state: str,
        work_notes: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        key = (state or "").strip().lower()
        if key not in CHANGE_STATES and key not in set(CHANGE_STATES.values()):
            return {
                "ok": False,
                "error": (
                    f"Unknown change state '{state}'. "
                    f"Valid options: {', '.join(sorted(CHANGE_STATES.keys()))}"
                ),
                "valid_states": sorted(CHANGE_STATES.keys()),
            }
        numeric = CHANGE_STATES.get(key, key)
        payload: dict[str, Any] = {"state": numeric}
        if work_notes:
            payload["work_notes"] = work_notes
        result = await self._table_patch("change_request", sys_id, payload)
        if result.get("ok"):
            result["state"] = key
            store_idempotent(idempotency_key, {**result, "reused": False})
        return result

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
            if action in ("create_incident", "create"):
                result = await self.create_incident(
                    short_description=str(params.get("short_description") or params.get("title") or ""),
                    description=str(params.get("description") or ""),
                    urgency=str(params.get("urgency") or "3"),
                    impact=str(params.get("impact") or "3"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
            if action == "create_change_request":
                result = await self.create_change_request(
                    short_description=str(params.get("short_description") or ""),
                    description=str(params.get("description") or ""),
                    risk=str(params.get("risk") or "moderate"),
                    planned_start=params.get("planned_start"),
                    planned_end=params.get("planned_end"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
            if action == "update_change_state":
                result = await self.update_change_state(
                    str(params.get("sys_id") or ""),
                    str(params.get("state") or ""),
                    work_notes=params.get("work_notes"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "servicenow", "action": action, "result": result}
        except ConnectorNotConfigured as exc:
            return {"ok": False, "tool": "servicenow", "action": action, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "tool": "servicenow", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
