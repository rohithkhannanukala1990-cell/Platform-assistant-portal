"""PagerDuty connector — incidents / oncalls via python-pagerduty (account-scoped credentials)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from pagerduty import RestApiV2Client

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

    def _client(self) -> RestApiV2Client | None:
        key = self._api_key()
        if not key:
            return None
        return RestApiV2Client(key)

    async def ping(self) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            client = self._client()
            if not client:
                return {
                    "ok": False,
                    "error": {"type": "not_configured", "message": "PagerDuty API key missing"},
                }
            try:
                abilities = client.get("/abilities")
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
            client = self._client()
            if not client:
                return []
            statuses = [s.strip() for s in status.split(",") if s.strip()] or ["triggered"]
            params: dict[str, Any] = {"statuses[]": statuses, "limit": limit}
            if date_range:
                params["date_range"] = date_range
            incidents = client.list_all("incidents", params=params)
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

    async def list_oncalls(
        self,
        limit: int = 20,
        *,
        schedule_id: str | None = None,
        service_id: str | None = None,
    ) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            client = self._client()
            if not client:
                return []
            params: dict[str, Any] = {"limit": limit}
            if schedule_id:
                params["schedule_ids[]"] = schedule_id
            if service_id:
                params["service_ids[]"] = service_id
            rows = client.list_all("oncalls", params=params)
            out: list[dict[str, Any]] = []
            for row in rows:
                user = row.get("user") or {}
                schedule = row.get("schedule") or {}
                escalation = row.get("escalation_policy") or {}
                service = row.get("service") or {}
                out.append(
                    {
                        "user": user.get("summary") or user.get("id"),
                        "user_id": user.get("id"),
                        "schedule": schedule.get("summary") or schedule.get("id"),
                        "schedule_id": schedule.get("id"),
                        "escalation_policy": escalation.get("summary") or escalation.get("id"),
                        "service": service.get("summary") or service.get("id"),
                        "service_id": service.get("id"),
                        "start": row.get("start"),
                        "end": row.get("end"),
                        "html_url": schedule.get("html_url") or user.get("html_url"),
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
            client = self._client()
            if not client:
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
            resp = client.rpost("incidents", json=body, headers=headers)
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
            client = self._client()
            if not client:
                return {"success": False}
            from_user = self._from_email()
            headers = {"From": from_user} if from_user else None
            client.rput(
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
            client = self._client()
            if not client:
                return {"success": False}
            from_user = self._from_email()
            headers = {"From": from_user} if from_user else None
            client.rput(
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

    async def list_schedules(self, limit: int = 50) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            client = self._client()
            if not client:
                return []
            rows = client.list_all("schedules", params={"limit": limit})
            out = []
            for s in rows:
                out.append(
                    {
                        "id": s.get("id"),
                        "name": s.get("name") or s.get("summary"),
                        "html_url": s.get("html_url"),
                        "time_zone": s.get("time_zone"),
                    }
                )
            return out[:limit]

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def get_schedule_with_rotations(
        self,
        schedule_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            client = self._client()
            if not client:
                return {}
            params: dict[str, Any] = {}
            if since:
                params["since"] = since
            if until:
                params["until"] = until
            resp = client.rget(f"/schedules/{schedule_id}", params=params or None)
            sched = resp if isinstance(resp, dict) else {}
            # Prefer final_schedule rendered entries when present
            final = (sched.get("final_schedule") or {}).get("rendered_schedule_entries") or []
            coverage = []
            for e in final:
                user = e.get("user") or {}
                coverage.append(
                    {
                        "user_id": user.get("id"),
                        "user": user.get("summary"),
                        "start": e.get("start"),
                        "end": e.get("end"),
                    }
                )
            return {
                "id": sched.get("id") or schedule_id,
                "name": sched.get("name") or sched.get("summary"),
                "schedule_layers": sched.get("schedule_layers") or [],
                "rendered_coverage": coverage,
                "final_schedule": coverage,
            }

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return {"id": schedule_id, "rendered_coverage": [], "final_schedule": []}

    async def list_escalation_policies(self, limit: int = 50) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            client = self._client()
            if not client:
                return []
            rows = client.list_all("escalation_policies", params={"limit": limit})
            out = []
            for p in rows:
                rules = []
                for r in p.get("escalation_rules") or []:
                    targets = []
                    for t in r.get("targets") or []:
                        targets.append(
                            {
                                "id": t.get("id"),
                                "type": t.get("type"),
                                "summary": t.get("summary"),
                            }
                        )
                    rules.append(
                        {
                            "id": r.get("id"),
                            "escalation_delay_in_minutes": r.get("escalation_delay_in_minutes"),
                            "targets": targets,
                        }
                    )
                out.append(
                    {
                        "id": p.get("id"),
                        "name": p.get("name") or p.get("summary"),
                        "rules": rules,
                        "escalation_rules": rules,
                    }
                )
            return out[:limit]

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def get_current_oncall(
        self, *, schedule_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self.list_oncalls(limit=limit, schedule_id=schedule_id)

    async def create_schedule_override(
        self,
        schedule_id: str,
        user_id: str,
        start: str,
        end: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent

        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        if not self.configured:
            raise ConnectorNotConfigured("pagerduty")

        def _sync() -> dict[str, Any]:
            client = self._client()
            if not client:
                raise ConnectorNotConfigured("pagerduty")
            body = {
                "override": {
                    "start": start,
                    "end": end,
                    "user": {"id": user_id, "type": "user_reference"},
                }
            }
            resp = client.rpost(f"/schedules/{schedule_id}/overrides", json=body)
            return {
                "ok": True,
                "id": resp.get("id"),
                "schedule_id": schedule_id,
                "user_id": user_id,
                "start": start,
                "end": end,
                "url": resp.get("html_url"),
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

    async def update_escalation_policy(
        self,
        policy_id: str,
        rules: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent

        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        if not self.configured:
            raise ConnectorNotConfigured("pagerduty")

        def _sync() -> dict[str, Any]:
            client = self._client()
            if not client:
                raise ConnectorNotConfigured("pagerduty")
            body = {
                "escalation_policy": {
                    "id": policy_id,
                    "type": "escalation_policy",
                    "escalation_rules": rules,
                }
            }
            resp = client.rput(f"/escalation_policies/{policy_id}", json=body)
            return {
                "ok": True,
                "id": resp.get("id") or policy_id,
                "rules": rules,
                "url": resp.get("html_url"),
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

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
            if action == "list_schedules":
                result = await self.list_schedules(limit=int(params.get("limit", 50)))
                return {"ok": True, "tool": "pagerduty", "action": action, "result": result}
            if action == "create_schedule_override":
                result = await self.create_schedule_override(
                    params.get("schedule_id", ""),
                    params.get("user_id", ""),
                    params.get("start", ""),
                    params.get("end", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "pagerduty", "action": action, "result": result}
            if action == "update_escalation_policy":
                result = await self.update_escalation_policy(
                    params.get("policy_id", ""),
                    params.get("rules") or [],
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "pagerduty", "action": action, "result": result}
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
