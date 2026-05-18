"""GitHub connector — REST API via httpx."""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Optional

import httpx

from .registry import GitHubConnector as _BaseGitHub

_API_BASE = "https://api.github.com"


class GitHubConnector(_BaseGitHub):
    def _headers(self) -> dict[str, str]:
        token = os.getenv("GITHUB_TOKEN", "")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{_API_BASE}{path}",
                headers=self._headers(),
                params=params or {},
            )
            if resp.status_code >= 400:
                return None
            return resp.json()

    @staticmethod
    def _decode_content(data: Any) -> Optional[str]:
        if not isinstance(data, dict):
            return None
        content = data.get("content")
        if not content:
            return None
        if data.get("encoding") == "base64":
            try:
                return base64.b64decode(content).decode("utf-8", errors="replace")
            except Exception:
                return None
        return str(content)

    async def list_pull_requests(
        self,
        repo: str,
        state: str = "open",
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        try:
            data = await self._get(
                f"/repos/{repo}/pulls",
                params={"state": state, "per_page": per_page},
            )
            if not isinstance(data, list):
                return []
            return [
                {
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "user": (pr.get("user") or {}).get("login"),
                    "html_url": pr.get("html_url"),
                    "created_at": pr.get("created_at"),
                    "updated_at": pr.get("updated_at"),
                }
                for pr in data
            ]
        except Exception:
            return []

    async def list_workflow_runs(
        self,
        repo: str,
        status: str = "failure",
        per_page: int = 20,
    ) -> list[dict[str, Any]]:
        try:
            data = await self._get(
                f"/repos/{repo}/actions/runs",
                params={"status": status, "per_page": per_page},
            )
            if not isinstance(data, dict):
                return []
            runs = data.get("workflow_runs") or []
            return [
                {
                    "id": run.get("id"),
                    "name": run.get("name"),
                    "status": run.get("status"),
                    "conclusion": run.get("conclusion"),
                    "html_url": run.get("html_url"),
                    "created_at": run.get("created_at"),
                    "head_branch": run.get("head_branch"),
                }
                for run in runs
            ]
        except Exception:
            return []

    async def get_readme(self, repo: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/readme")
            return self._decode_content(data)
        except Exception:
            return None

    async def get_file_contents(self, repo: str, path: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/contents/{path}")
            return self._decode_content(data)
        except Exception:
            return None

    async def get_latest_tag(self, repo: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/tags", params={"per_page": 1})
            if not isinstance(data, list) or not data:
                return None
            first = data[0]
            return first.get("name") if isinstance(first, dict) else None
        except Exception:
            return None

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            repo = params.get("repo", "")
            if action == "list_pull_requests":
                result = await self.list_pull_requests(
                    repo,
                    state=params.get("state", "open"),
                    per_page=int(params.get("per_page", 30)),
                )
                return {"ok": True, "tool": "github", "action": action, "result": result}
            if action == "list_workflow_runs":
                result = await self.list_workflow_runs(
                    repo,
                    status=params.get("status", "failure"),
                    per_page=int(params.get("per_page", 20)),
                )
                return {"ok": True, "tool": "github", "action": action, "result": result}
            if action == "get_readme":
                result = await self.get_readme(repo)
                return {"ok": result is not None, "tool": "github", "action": action, "result": result}
            if action == "get_file_contents":
                result = await self.get_file_contents(repo, params.get("path", ""))
                return {"ok": result is not None, "tool": "github", "action": action, "result": result}
            if action == "get_latest_tag":
                result = await self.get_latest_tag(repo)
                return {"ok": True, "tool": "github", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "github", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
