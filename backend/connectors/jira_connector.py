"""Jira connector — issues via jira Python library."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from jira import JIRA

from .registry import JiraConnector as _BaseJira


class JiraConnector(_BaseJira):
    def _client(self) -> JIRA | None:
        url = os.getenv("JIRA_URL", "")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        if not url or not email or not token:
            return None
        return JIRA(server=url, basic_auth=(email, token))

    async def create_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        issue_type: str = "Task",
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            jira = self._client()
            if not jira:
                return {}
            issue = jira.create_issue(
                {
                    "project": {"key": project_key},
                    "summary": summary,
                    "description": description,
                    "issuetype": {"name": issue_type},
                }
            )
            url = os.getenv("JIRA_URL", "").rstrip("/")
            return {
                "key": issue.key,
                "id": issue.id,
                "url": f"{url}/browse/{issue.key}" if url else None,
            }

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    async def list_issues(
        self,
        project_key: str,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            jira = self._client()
            if not jira:
                return []
            jql = f"project={project_key}"
            if status:
                jql += f" AND status='{status}'"
            issues = jira.search_issues(jql, maxResults=50)
            out: list[dict[str, Any]] = []
            for issue in issues:
                assignee = getattr(issue.fields, "assignee", None)
                out.append(
                    {
                        "key": issue.key,
                        "summary": issue.fields.summary,
                        "status": str(issue.fields.status),
                        "assignee": assignee.displayName if assignee else None,
                        "created": str(issue.fields.created),
                    }
                )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            jira = self._client()
            if not jira:
                return {}
            issue = jira.issue(issue_key)
            assignee = getattr(issue.fields, "assignee", None)
            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "status": str(issue.fields.status),
                "description": getattr(issue.fields, "description", None) or "",
                "assignee": assignee.displayName if assignee else None,
            }

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _sync)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "create_issue":
                result = await self.create_issue(
                    params.get("project_key", ""),
                    params.get("summary", ""),
                    params.get("description", ""),
                    params.get("issue_type", "Task"),
                )
                return {"ok": bool(result.get("key")), "tool": "jira", "action": action, "result": result}
            if action == "list_issues":
                result = await self.list_issues(
                    params.get("project_key", ""),
                    params.get("status"),
                )
                return {"ok": True, "tool": "jira", "action": action, "result": result}
            if action == "get_issue":
                result = await self.get_issue(params.get("issue_key", ""))
                return {"ok": bool(result.get("key")), "tool": "jira", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "jira", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
