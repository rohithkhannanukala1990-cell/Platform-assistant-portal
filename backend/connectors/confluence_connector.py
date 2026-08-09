"""Confluence connector — pages create/update/search (HITL write path)."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

import httpx

from ..services.ssrf import assert_safe_outbound_url
from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
from .registry import BaseConnector


class ConfluenceConnector(BaseConnector):
    def _base_url(self) -> str:
        raw = (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or ""
        ).strip().rstrip("/")
        if raw and not raw.startswith("http"):
            raw = f"https://{raw}"
        return raw

    def _email(self) -> str:
        return (
            self.account.get("account_identifier")
            or self.account.get("email")
            or self.account.get("username")
            or ""
        ).strip()

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
        return bool(self._base_url() and self._email() and self._token())

    def _require_configured(self) -> None:
        if not self.configured:
            raise ConnectorNotConfigured("Confluence")

    def _auth_header(self) -> dict[str, str]:
        raw = f"{self._email()}:{self._token()}".encode("utf-8")
        return {
            "Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _page_url(self, page_id: str, space_key: str | None = None) -> str:
        base = self._base_url()
        if not base or not page_id:
            return ""
        if space_key:
            return f"{base}/spaces/{space_key}/pages/{page_id}"
        return f"{base}/pages/viewpage.action?pageId={page_id}"

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
                headers=self._auth_header(),
                json=json_body,
                params=params,
            )
            data: Any = {}
            try:
                data = resp.json()
            except Exception:
                data = {"raw": (resp.text or "")[:500]}
            if resp.status_code == 409:
                return {
                    "ok": False,
                    "status_code": 409,
                    "error": "conflict",
                    "message": (
                        "Page changed upstream — version is stale. "
                        "Re-fetch the page and retry with the current version."
                    ),
                }
            if resp.status_code >= 400:
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("message") or data.get("errorMessages") or data)[:400]
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": msg or f"HTTP {resp.status_code}",
                }
            if isinstance(data, dict):
                data.setdefault("ok", True)
                return data
            return {"ok": True, "data": data}

    async def create_page(
        self,
        space_key: str,
        title: str,
        body_html: str,
        parent_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        body: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {"value": body_html or "", "representation": "storage"},
            },
        }
        if parent_id:
            body["ancestors"] = [{"id": str(parent_id)}]
        data = await self._request("POST", "/wiki/rest/api/content", json_body=body)
        # Some Confluence Cloud hosts use /rest/api/content without /wiki
        if data.get("ok") is False and data.get("status_code") == 404:
            data = await self._request("POST", "/rest/api/content", json_body=body)
        if data.get("ok") is False:
            return data
        page_id = str(data.get("id") or "")
        out = {
            "ok": True,
            "id": page_id,
            "title": data.get("title") or title,
            "space_key": space_key,
            "url": self._page_url(page_id, space_key),
            "version": ((data.get("version") or {}).get("number")),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def update_page(
        self,
        page_id: str,
        title: str,
        body_html: str,
        version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        body = {
            "id": str(page_id),
            "type": "page",
            "title": title,
            "body": {
                "storage": {"value": body_html or "", "representation": "storage"},
            },
            "version": {"number": int(version) + 1},
        }
        data = await self._request(
            "PUT", f"/wiki/rest/api/content/{quote(str(page_id))}", json_body=body
        )
        if data.get("ok") is False and data.get("status_code") == 404:
            data = await self._request(
                "PUT", f"/rest/api/content/{quote(str(page_id))}", json_body=body
            )
        if data.get("status_code") == 409 or data.get("error") == "conflict":
            return {
                "ok": False,
                "status_code": 409,
                "error": "conflict",
                "message": (
                    "Page changed upstream — version is stale. "
                    "Re-fetch the page and retry with the current version."
                ),
                "url": self._page_url(str(page_id)),
            }
        if data.get("ok") is False:
            return data
        out = {
            "ok": True,
            "id": str(data.get("id") or page_id),
            "title": data.get("title") or title,
            "url": self._page_url(str(data.get("id") or page_id)),
            "version": ((data.get("version") or {}).get("number")),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def get_page(self, page_id: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            f"/wiki/rest/api/content/{quote(str(page_id))}",
            params={"expand": "body.storage,version,space"},
        )
        if data.get("ok") is False and data.get("status_code") == 404:
            data = await self._request(
                "GET",
                f"/rest/api/content/{quote(str(page_id))}",
                params={"expand": "body.storage,version,space"},
            )
        if data.get("ok") is False:
            return data
        space = (data.get("space") or {}).get("key")
        return {
            "ok": True,
            "id": str(data.get("id") or page_id),
            "title": data.get("title"),
            "space_key": space,
            "version": ((data.get("version") or {}).get("number")),
            "body_html": (((data.get("body") or {}).get("storage") or {}).get("value")),
            "url": self._page_url(str(data.get("id") or page_id), space),
        }

    async def search_pages(
        self, space_key: str, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        cql = f'space="{space_key}" AND text ~ "{query}"'
        data = await self._request(
            "GET",
            "/wiki/rest/api/content/search",
            params={"cql": cql, "limit": min(int(limit or 10), 50)},
        )
        if data.get("ok") is False and data.get("status_code") == 404:
            data = await self._request(
                "GET",
                "/rest/api/content/search",
                params={"cql": cql, "limit": min(int(limit or 10), 50)},
            )
        out = []
        for row in (data.get("results") or []) if isinstance(data, dict) else []:
            pid = str(row.get("id") or "")
            out.append(
                {
                    "id": pid,
                    "title": row.get("title"),
                    "url": self._page_url(pid, space_key),
                }
            )
        return out

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "create_page":
                result = await self.create_page(
                    params.get("space_key", ""),
                    params.get("title", ""),
                    params.get("body_html", ""),
                    parent_id=params.get("parent_id"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "confluence", "action": action, "result": result}
            if action == "update_page":
                result = await self.update_page(
                    params.get("page_id", ""),
                    params.get("title", ""),
                    params.get("body_html", ""),
                    int(params.get("version") or 0),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "confluence", "action": action, "result": result}
            if action == "get_page":
                result = await self.get_page(params.get("page_id", ""))
                return {"ok": bool(result.get("ok")), "tool": "confluence", "action": action, "result": result}
            if action == "search_pages":
                result = await self.search_pages(
                    params.get("space_key", ""),
                    params.get("query", ""),
                    limit=int(params.get("limit") or 10),
                )
                return {"ok": True, "tool": "confluence", "action": action, "result": result}
        except ConnectorNotConfigured as exc:
            return {"ok": False, "tool": "confluence", "action": action, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "tool": "confluence", "action": action, "error": str(exc)[:300]}
        return await super().execute_action(action, params)
