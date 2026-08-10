"""Okta connector — users/groups read + HITL write (group membership, deactivate)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from ..services.ssrf import assert_safe_outbound_url
from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
from .registry import BaseConnector


class OktaConnector(BaseConnector):
    def _base_url(self) -> str:
        raw = (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or self.account.get("domain")
            or ""
        ).strip().rstrip("/")
        if raw and not raw.startswith("http"):
            raw = f"https://{raw}"
        return raw

    def _token(self) -> str:
        return (
            self.account.get("api_token")
            or self.account.get("token")
            or self.account.get("api_key")
            or self.account.get("credentials_vault_ref")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._base_url() and self._token())

    def _require_configured(self) -> None:
        if not self.configured:
            raise ConnectorNotConfigured("Okta")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"SSWS {self._token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        self._require_configured()
        url = f"{self._base_url()}{path}"
        assert_safe_outbound_url(url)
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.request(
                method,
                url,
                headers=self._auth_headers(),
                json=json_body,
                params=params,
            )
        # 204 No Content — success
        if resp.status_code == 204:
            return {"ok": True, "status_code": 204}
        data: Any = {}
        try:
            data = resp.json()
        except Exception:
            data = {"raw": (resp.text or "")[:500]}
        if resp.status_code >= 400:
            msg = ""
            if isinstance(data, dict):
                msg = str(
                    data.get("errorSummary")
                    or data.get("errorCauses")
                    or data.get("message")
                    or data
                )[:400]
            return {
                "ok": False,
                "status_code": resp.status_code,
                "error": msg or f"HTTP {resp.status_code}",
            }
        if isinstance(data, list):
            return {"ok": True, "list": data}
        if isinstance(data, dict):
            data.setdefault("ok", True)
            return data
        return {"ok": True, "data": data}

    async def get_user(self, email_or_id: str) -> dict[str, Any]:
        ident = quote(str(email_or_id or "").strip(), safe="")
        data = await self._request("GET", f"/api/v1/users/{ident}")
        if data.get("ok") is False:
            return data
        profile = data.get("profile") or {}
        return {
            "ok": True,
            "id": data.get("id"),
            "email": profile.get("email"),
            "login": profile.get("login"),
            "first_name": profile.get("firstName"),
            "last_name": profile.get("lastName"),
            "status": data.get("status"),
        }

    async def list_groups(
        self, query: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": min(max(1, int(limit or 50)), 200)}
        if query:
            params["q"] = str(query)
        data = await self._request("GET", "/api/v1/groups", params=params)
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        if not rows and isinstance(data, dict) and data.get("ok") is False:
            return []
        out: list[dict[str, Any]] = []
        for row in rows or []:
            profile = row.get("profile") or {}
            out.append(
                {
                    "id": row.get("id"),
                    "name": profile.get("name"),
                    "description": profile.get("description"),
                    "type": row.get("type"),
                }
            )
        return out

    async def list_user_groups(self, user_id: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET", f"/api/v1/users/{quote(str(user_id), safe='')}/groups"
        )
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        out: list[dict[str, Any]] = []
        for row in rows or []:
            profile = row.get("profile") or {}
            out.append(
                {
                    "id": row.get("id"),
                    "name": profile.get("name"),
                    "type": row.get("type"),
                }
            )
        return out

    async def get_group(self, group_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET", f"/api/v1/groups/{quote(str(group_id), safe='')}"
        )
        if data.get("ok") is False:
            return data
        profile = data.get("profile") or {}
        return {
            "ok": True,
            "id": data.get("id"),
            "name": profile.get("name"),
            "description": profile.get("description"),
            "type": data.get("type"),
        }

    async def add_user_to_group(
        self,
        user_id: str,
        group_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        data = await self._request(
            "PUT",
            f"/api/v1/groups/{quote(str(group_id), safe='')}"
            f"/users/{quote(str(user_id), safe='')}",
        )
        if data.get("ok") is False:
            return data
        out = {
            "ok": True,
            "group_id": group_id,
            "user_id": user_id,
            "action": "added",
            "url": f"{self._base_url()}/admin/group/{group_id}",
        }
        store_idempotent(idempotency_key, out)
        return out

    async def remove_user_from_group(
        self,
        user_id: str,
        group_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        data = await self._request(
            "DELETE",
            f"/api/v1/groups/{quote(str(group_id), safe='')}"
            f"/users/{quote(str(user_id), safe='')}",
        )
        if data.get("ok") is False and data.get("status_code") != 404:
            return data
        out = {
            "ok": True,
            "group_id": group_id,
            "user_id": user_id,
            "action": "removed",
            "url": f"{self._base_url()}/admin/group/{group_id}",
        }
        store_idempotent(idempotency_key, out)
        return out

    async def deactivate_user(
        self,
        user_id: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        # Best practice: DEACTIVATE first (from ACTIVE), then optionally deactivate again
        # from PROVISIONED etc. Ignore 404 (already removed).
        data = await self._request(
            "POST",
            f"/api/v1/users/{quote(str(user_id), safe='')}/lifecycle/deactivate",
            params={"sendEmail": "false"},
        )
        if data.get("ok") is False and data.get("status_code") not in (404, 200, 204):
            return data
        out = {
            "ok": True,
            "user_id": user_id,
            "action": "deactivated",
            "url": f"{self._base_url()}/admin/user/profile/view/{user_id}",
        }
        store_idempotent(idempotency_key, out)
        return out

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "get_user":
                result = await self.get_user(params.get("email_or_id", ""))
                return {"ok": bool(result.get("ok")), "tool": "okta", "action": action, "result": result}
            if action == "list_groups":
                result = await self.list_groups(
                    query=params.get("query"),
                    limit=int(params.get("limit") or 50),
                )
                return {"ok": True, "tool": "okta", "action": action, "result": result}
            if action == "list_user_groups":
                result = await self.list_user_groups(params.get("user_id", ""))
                return {"ok": True, "tool": "okta", "action": action, "result": result}
            if action == "get_group":
                result = await self.get_group(params.get("group_id", ""))
                return {"ok": bool(result.get("ok")), "tool": "okta", "action": action, "result": result}
            if action == "add_user_to_group":
                result = await self.add_user_to_group(
                    params.get("user_id", ""),
                    params.get("group_id", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "okta", "action": action, "result": result}
            if action == "remove_user_from_group":
                result = await self.remove_user_from_group(
                    params.get("user_id", ""),
                    params.get("group_id", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "okta", "action": action, "result": result}
            if action == "deactivate_user":
                result = await self.deactivate_user(
                    params.get("user_id", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "okta", "action": action, "result": result}
        except ConnectorNotConfigured as exc:
            return {"ok": False, "tool": "okta", "action": action, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "tool": "okta", "action": action, "error": str(exc)[:300]}
        return await super().execute_action(action, params)
