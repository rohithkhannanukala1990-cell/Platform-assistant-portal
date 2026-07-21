"""GitHub connector — REST API via httpx."""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Optional

import httpx

from .registry import GitHubConnector as _BaseGitHub

_API_BASE = "https://api.github.com"


class GitHubAPIError(Exception):
    """Structured GitHub HTTP / network failure."""

    def __init__(self, error_type: str, message: str, status_code: int | None = None):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.error_type, "message": self.message}


def _map_status_to_error(status_code: int, body: str) -> GitHubAPIError:
    snippet = (body or "").strip()[:200]
    if status_code in (401, 403):
        return GitHubAPIError(
            "auth_failed",
            snippet or "Invalid or missing token",
            status_code=status_code,
        )
    if status_code == 404:
        return GitHubAPIError(
            "not_found",
            snippet or "GitHub resource not found",
            status_code=status_code,
        )
    if status_code == 429:
        return GitHubAPIError(
            "rate_limited",
            snippet or "GitHub API rate limit exceeded",
            status_code=status_code,
        )
    return GitHubAPIError(
        "network_error",
        snippet or f"GitHub API HTTP {status_code}",
        status_code=status_code,
    )


def _record_connector_error(error_type: str) -> None:
    try:
        from ..observability.metrics import CONNECTOR_ERRORS_TOTAL

        CONNECTOR_ERRORS_TOTAL.labels(
            connector="github",
            error_type=error_type,
        ).inc()
    except Exception:
        pass


class GitHubConnector(_BaseGitHub):
    def _headers(self) -> dict[str, str]:
        token = (
            (self.account or {}).get("token")
            or (self.account or {}).get("api_token")
            or os.getenv("GITHUB_TOKEN", "")
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # TODO: Return structured error codes (auth_failed, rate_limited, not_found, network_error) instead of None on HTTP errors
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{_API_BASE}{path}",
                    headers=self._headers(),
                    params=params or {},
                )
        except httpx.HTTPError as exc:
            raise GitHubAPIError(
                "network_error",
                f"GitHub network error: {exc}",
            ) from exc

        if resp.status_code >= 400:
            raise _map_status_to_error(resp.status_code, resp.text)
        try:
            return resp.json()
        except ValueError as exc:
            raise GitHubAPIError(
                "network_error",
                "GitHub returned a non-JSON response",
                status_code=resp.status_code,
            ) from exc

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
        except GitHubAPIError:
            raise
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
        except GitHubAPIError:
            raise
        except Exception:
            return []

    async def get_readme(self, repo: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/readme")
            return self._decode_content(data)
        except GitHubAPIError:
            raise
        except Exception:
            return None

    async def get_file_contents(self, repo: str, path: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/contents/{path}")
            return self._decode_content(data)
        except GitHubAPIError:
            raise
        except Exception:
            return None

    async def get_latest_tag(self, repo: str) -> Optional[str]:
        try:
            data = await self._get(f"/repos/{repo}/tags", params={"per_page": 1})
            if not isinstance(data, list) or not data:
                return None
            first = data[0]
            return first.get("name") if isinstance(first, dict) else None
        except GitHubAPIError:
            raise
        except Exception:
            return None

    # TODO: Wrap connector actions in try/except and return:
    # - ok: bool
    # - tool: "github"
    # - action: str
    # - result: data on success
    # - error: { type, message } on failure
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
                return {
                    "ok": result is not None,
                    "tool": "github",
                    "action": action,
                    "result": result,
                }
            if action == "get_file_contents":
                result = await self.get_file_contents(repo, params.get("path", ""))
                return {
                    "ok": result is not None,
                    "tool": "github",
                    "action": action,
                    "result": result,
                }
            if action == "get_latest_tag":
                result = await self.get_latest_tag(repo)
                return {"ok": True, "tool": "github", "action": action, "result": result}
            if action == "test_connection":
                data = await self._get("/rate_limit")
                return {"ok": True, "tool": "github", "action": action, "result": data}
        except GitHubAPIError as exc:
            _record_connector_error(exc.error_type)
            return {
                "ok": False,
                "tool": "github",
                "action": action,
                "error": exc.as_dict(),
            }
        except Exception as exc:
            _record_connector_error("network_error")
            return {
                "ok": False,
                "tool": "github",
                "action": action,
                "error": {"type": "network_error", "message": str(exc)},
            }
        return await super().execute_action(action, params)
