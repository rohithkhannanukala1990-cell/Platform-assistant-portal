"""PagerDuty connector — incidents / oncalls via pdpyras (account-scoped credentials)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pdpyras import APISession

from .registry import PagerDutyConnector as _BasePd


class PagerDutyConnector(_BasePd):
    def _api_key(self) -> str:
        return (
            self.account.get("api_key")
            or self.account.get("token")
            or self.account.get("api_token")
            or self.account.get("credentials_vault_ref")
            or os.getenv("PAGERDUTY_API_KEY", "")
        ).strip()

    def _from_email(self) -> str:
        return (
            self.account.get("account_identifier")
            or self.account.get("from_email")
            or os.getenv("PAGERDUTY_FROM_EMAIL", "")
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._api_key())

    def _session(self) -> APISession | None:
        key = self._api_key()
        if not key:
            return None
        return APISession(key)

    async def ping(self) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            session = self._session()
            if not session:
                return {
                    "ok": False,
                    "error": {"type": "not_configured", "message": "PagerDuty API key missing"},
                }
            try:
                abilities = session.get("/abilities")
                return {"ok": True, "abilities": abilities if isinstance(abilities, list) else True}
            except Exception as exc:
                msg = str(exc)
                err_type = "auth_failed" if "401" in msg or "403" in msg else "network_error"
                return {"ok": False, "error": {"type": err_type, "message": msg}}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

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
            statuses = [s.strip() for s in status.split(",") if s.strip()] or ["triggered"]
            params: dict[str, Any] = {"statuses[]": statuses, "limit": limit}
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
                        "status": inc.get("status"),
                        "service": service.get("summary") or service.get("id"),
                        "urgency": inc.get("urgency"),
                        "created_at": inc.get("created_at"),
                        "html_url": inc.get("html_url"),
                    }
                )
            return out[:limit]

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def list_oncalls(self, limit: int = 20) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            session = self._session()
            if not session:
                return []
            rows = session.list_all("oncalls", params={"limit": limit})
            out: list[dict[str, Any]] = []
            for row in rows:
                user = row.get("user") or {}
                schedule = row.get("schedule") or {}
                escalation = row.get("escalation_policy") or {}
                out.append(
                    {
                        "user": user.get("summary") or user.get("id"),
                        "schedule": schedule.get("summary") or schedule.get("id"),
                        "escalation_policy": escalation.get("summary") or escalation.get("id"),
                        "start": row.get("start"),
                        "end": row.get("end"),
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
            from_user = self._from_email()
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
            from_user = self._from_email()
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
            from_user = self._from_email()
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
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "pagerduty", "action": action, "result": result}
            if action == "list_incidents":
                result = await self.list_incidents(
                    status=params.get("status", "triggered"),
                    limit=int(params.get("limit", 20)),
                    date_range=params.get("date_range"),
                )
                return {"ok": True, "tool": "pagerduty", "action": action, "result": result}
            if action == "list_oncalls":
                result = await self.list_oncalls(limit=int(params.get("limit", 20)))
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
