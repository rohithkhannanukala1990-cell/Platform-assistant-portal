"""PagerDuty connector — incidents via pdpyras."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pdpyras import APISession

from .registry import PagerDutyConnector as _BasePd


class PagerDutyConnector(_BasePd):
    def _session(self) -> APISession | None:
        key = os.getenv("PAGERDUTY_API_KEY", "")
        if not key:
            return None
        return APISession(key)

    async def list_incidents(
        self,
        status: str = "triggered",
        limit: int = 20,
        date_range: str | None = None,
    ) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            session = self._session()
            if not session:
                return []
            params: dict[str, Any] = {"statuses[]": [status], "limit": limit}
            if date_range:
                params["date_range"] = date_range
            incidents = session.list_all("incidents", params=params)
            out: list[dict[str, Any]] = []
            for inc in incidents:
                service = inc.get("service") or {}
                out.append(
                    {
                        "id": inc.get("id"),
                        "title": inc.get("title"),
                        "service": service.get("summary") or service.get("id"),
                        "urgency": inc.get("urgency"),
                        "created_at": inc.get("created_at"),
                    }
                )
            return out[:limit]

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def create_incident(
        self,
        title: str,
        service_id: str,
        urgency: str = "high",
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            session = self._session()
            if not session:
                return {}
            from_user = os.getenv("PAGERDUTY_FROM_EMAIL", "")
            body = {
                "incident": {
                    "type": "incident",
                    "title": title,
                    "service": {"id": service_id, "type": "service_reference"},
                    "urgency": urgency,
                    "body": {"type": "incident_body", "details": title},
                }
            }
            headers = {"From": from_user} if from_user else None
            resp = session.rpost("incidents", json=body, headers=headers)
            return {
                "id": resp.get("id"),
                "title": resp.get("title"),
                "status": resp.get("status"),
            }

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    async def acknowledge_incident(self, incident_id: str) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            session = self._session()
            if not session:
                return {"success": False}
            from_user = os.getenv("PAGERDUTY_FROM_EMAIL", "")
            headers = {"From": from_user} if from_user else None
            session.rput(
                f"incidents/{incident_id}",
                json={
                    "incident": {
                        "type": "incident_reference",
                        "status": "acknowledged",
                    }
                },
                headers=headers,
            )
            return {"success": True}

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return {"success": False}

    async def resolve_incident(self, incident_id: str) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            session = self._session()
            if not session:
                return {"success": False}
            from_user = os.getenv("PAGERDUTY_FROM_EMAIL", "")
            headers = {"From": from_user} if from_user else None
            session.rput(
                f"incidents/{incident_id}",
                json={
                    "incident": {
                        "type": "incident_reference",
                        "status": "resolved",
                    }
                },
                headers=headers,
            )
            return {"success": True}

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return {"success": False}

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "list_incidents":
                result = await self.list_incidents(
                    status=params.get("status", "triggered"),
                    limit=int(params.get("limit", 20)),
                    date_range=params.get("date_range"),
                )
                return {"ok": True, "tool": "pagerduty", "action": action, "result": result}
            if action == "create_incident":
                result = await self.create_incident(
                    params.get("title", ""),
                    params.get("service_id", ""),
                    params.get("urgency", "high"),
                )
                return {"ok": bool(result.get("id")), "tool": "pagerduty", "action": action, "result": result}
            if action == "acknowledge_incident":
                result = await self.acknowledge_incident(params.get("incident_id", ""))
                return {"ok": result.get("success", False), "tool": "pagerduty", "action": action, "result": result}
            if action == "resolve_incident":
                result = await self.resolve_incident(params.get("incident_id", ""))
                return {"ok": result.get("success", False), "tool": "pagerduty", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "pagerduty", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
