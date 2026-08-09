"""Jira connector — issue create / transition / comment / link (HITL write path)."""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

from ..services.ssrf import assert_safe_outbound_url
from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
from .registry import JiraConnector as _BaseJira


class JiraConnector(_BaseJira):
    def _base_url(self) -> str:
        raw = (
            self.account.get("instance_url")
            or self.account.get("base_url")
            or os.getenv("JIRA_URL")
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
            or os.getenv("JIRA_EMAIL")
            or ""
        ).strip()

    def _token(self) -> str:
        return (
            self.account.get("api_token")
            or self.account.get("token")
            or self.account.get("api_key")
            or self.account.get("credentials_vault_ref")
            or os.getenv("JIRA_API_TOKEN")
            or ""
        ).strip()

    @property
    def configured(self) -> bool:
        return bool(self._base_url() and self._email() and self._token())

    def _require_configured(self) -> None:
        if not self.configured:
            raise ConnectorNotConfigured("Jira")

    def _auth_header(self) -> dict[str, str]:
        raw = f"{self._email()}:{self._token()}".encode("utf-8")
        return {
            "Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _browse_url(self, issue_key: str) -> str:
        base = self._base_url()
        return f"{base}/browse/{issue_key}" if base and issue_key else ""

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
            if resp.status_code >= 400:
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("errorMessages") or data.get("message") or data)[:400]
                return {
                    "ok": False,
                    "status_code": resp.status_code,
                    "error": msg or f"HTTP {resp.status_code}",
                }
            if isinstance(data, dict):
                data.setdefault("ok", True)
                return data
            return {"ok": True, "data": data}

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
        labels: list[str] | None = None,
        priority: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type or "Task"},
        }
        if labels:
            fields["labels"] = list(labels)
        if priority:
            fields["priority"] = {"name": priority}

        data = await self._request("POST", "/rest/api/2/issue", json_body={"fields": fields})
        if not data.get("ok", True) and data.get("error"):
            return data
        key = data.get("key") or ""
        out = {
            "ok": True,
            "key": key,
            "id": data.get("id"),
            "url": self._browse_url(key),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def transition_issue(
        self,
        issue_key: str,
        transition_name: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        transitions = await self._request(
            "GET", f"/rest/api/2/issue/{issue_key}/transitions"
        )
        available = []
        if isinstance(transitions, dict):
            for t in transitions.get("transitions") or []:
                available.append(
                    {"id": t.get("id"), "name": t.get("name")}
                )
        needle = (transition_name or "").strip().lower()
        match = next(
            (t for t in available if str(t.get("name") or "").strip().lower() == needle),
            None,
        )
        if not match:
            names = [str(t.get("name")) for t in available]
            return {
                "ok": False,
                "error": (
                    f"Transition '{transition_name}' is not available for {issue_key}. "
                    f"Available: {', '.join(names) if names else '(none)'}"
                ),
                "available_transitions": names,
                "url": self._browse_url(issue_key),
            }

        data = await self._request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/transitions",
            json_body={"transition": {"id": match["id"]}},
        )
        if data.get("ok") is False:
            return data
        out = {
            "ok": True,
            "key": issue_key,
            "transition": match.get("name"),
            "url": self._browse_url(issue_key),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def comment_on_issue(
        self,
        issue_key: str,
        body: str,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        data = await self._request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/comment",
            json_body={"body": body},
        )
        if data.get("ok") is False:
            return data
        out = {
            "ok": True,
            "key": issue_key,
            "comment_id": data.get("id"),
            "url": self._browse_url(issue_key),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def link_issues(
        self,
        from_key: str,
        to_key: str,
        link_type: str = "Relates",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}
        data = await self._request(
            "POST",
            "/rest/api/2/issueLink",
            json_body={
                "type": {"name": link_type or "Relates"},
                "inwardIssue": {"key": from_key},
                "outwardIssue": {"key": to_key},
            },
        )
        if data.get("ok") is False:
            return data
        out = {
            "ok": True,
            "from_key": from_key,
            "to_key": to_key,
            "link_type": link_type,
            "url": self._browse_url(from_key),
            "reused": False,
        }
        store_idempotent(idempotency_key, out)
        return out

    async def list_issues(self, project_key: str, status: str | None = None) -> list[dict[str, Any]]:
        jql = f"project={project_key}"
        if status:
            jql += f" AND status='{status}'"
        data = await self._request(
            "GET",
            "/rest/api/2/search",
            params={"jql": jql, "maxResults": 50},
        )
        out = []
        for issue in (data.get("issues") or []) if isinstance(data, dict) else []:
            fields = issue.get("fields") or {}
            out.append(
                {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "status": ((fields.get("status") or {}).get("name")),
                }
            )
        return out

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        data = await self._request("GET", f"/rest/api/2/issue/{issue_key}")
        if data.get("ok") is False:
            return data
        fields = data.get("fields") or {}
        return {
            "ok": True,
            "key": data.get("key") or issue_key,
            "summary": fields.get("summary"),
            "status": ((fields.get("status") or {}).get("name")),
            "description": fields.get("description") or "",
            "url": self._browse_url(data.get("key") or issue_key),
        }

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "create_issue":
                result = await self.create_issue(
                    params.get("project_key", ""),
                    params.get("summary", ""),
                    params.get("description", ""),
                    params.get("issue_type", "Task"),
                    labels=params.get("labels"),
                    priority=params.get("priority"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "jira", "action": action, "result": result}
            if action == "transition_issue":
                result = await self.transition_issue(
                    params.get("issue_key", ""),
                    params.get("transition_name", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "jira", "action": action, "result": result}
            if action == "comment_on_issue":
                result = await self.comment_on_issue(
                    params.get("issue_key", ""),
                    params.get("body", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "jira", "action": action, "result": result}
            if action == "link_issues":
                result = await self.link_issues(
                    params.get("from_key", ""),
                    params.get("to_key", ""),
                    params.get("link_type", "Relates"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "jira", "action": action, "result": result}
            if action == "list_issues":
                result = await self.list_issues(params.get("project_key", ""), params.get("status"))
                return {"ok": True, "tool": "jira", "action": action, "result": result}
            if action == "get_issue":
                result = await self.get_issue(params.get("issue_key", ""))
                return {"ok": bool(result.get("ok", True)), "tool": "jira", "action": action, "result": result}
        except ConnectorNotConfigured as exc:
            return {"ok": False, "tool": "jira", "action": action, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "tool": "jira", "action": action, "error": str(exc)[:300]}
        return await super().execute_action(action, params)
