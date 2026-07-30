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


def _mask_secret(message: str, secret: str | None) -> str:
    """Never leak tokens into exception/log text."""
    text = str(message or "")
    if secret and len(secret) >= 8 and secret in text:
        text = text.replace(secret, "***")
    # Common PAT prefixes
    for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"):
        if prefix in text:
            import re as _re

            text = _re.sub(rf"{prefix}[A-Za-z0-9_]+", f"{prefix}***", text)
    return text


def _map_status_to_error(status_code: int, body: str, token: str | None = None) -> GitHubAPIError:
    snippet = _mask_secret((body or "").strip()[:200], token)
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
    def _token(self) -> str:
        a = self.account or {}
        return str(
            a.get("token")
            or a.get("api_token")
            or a.get("credentials_vault_ref")
            or os.getenv("GITHUB_TOKEN", "")
            or ""
        ).strip()

    def _headers(self) -> dict[str, str]:
        token = self._token()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _do_test(self) -> dict[str, Any]:
        """Live auth check via /rate_limit (read-only)."""
        if not self._token():
            return {
                "connected": False,
                "error": "Missing GitHub token",
                "details": {"error_type": "auth_failed"},
            }
        try:
            data = await self._get("/rate_limit")
            resources = (data or {}).get("resources") if isinstance(data, dict) else {}
            core = (resources or {}).get("core") if isinstance(resources, dict) else {}
            return {
                "connected": True,
                "details": {
                    "instance_url": (self.account or {}).get("instance_url") or _API_BASE,
                    "org": (self.account or {}).get("account_identifier"),
                    "rate_limit_remaining": (core or {}).get("remaining"),
                },
            }
        except GitHubAPIError as exc:
            return {
                "connected": False,
                "error": _mask_secret(exc.message, self._token()),
                "details": {"error_type": exc.error_type},
            }

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        operation: str | None = None,
    ) -> Any:
        token = self._token()
        op = operation or self._operation_from_path(path)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_API_BASE}{path}",
                    headers=self._headers(),
                    params=params or {},
                )
        except httpx.HTTPError as exc:
            self._record_api(op, "network_error")
            raise GitHubAPIError(
                "network_error",
                _mask_secret(f"GitHub network error: {exc}", token),
            ) from exc

        if resp.status_code >= 400:
            err = _map_status_to_error(resp.status_code, resp.text, token=token)
            self._record_api(op, err.error_type)
            raise err
        try:
            data = resp.json()
        except ValueError as exc:
            self._record_api(op, "network_error")
            raise GitHubAPIError(
                "network_error",
                "GitHub returned a non-JSON response",
                status_code=resp.status_code,
            ) from exc
        self._record_api(op, "ok")
        return data

    @staticmethod
    def _operation_from_path(path: str) -> str:
        p = (path or "").strip("/")
        if p.startswith("user/repos") or (
            p.startswith("orgs/") and "/repos" in p and "/pulls" not in p and "/actions" not in p
        ):
            return "list_repos"
        if "/pulls/" in p and p.rstrip("/").endswith("/files"):
            return "list_pull_request_files"
        if "/pulls/" in p:
            return "get_pull_request"
        if p.endswith("/pulls") or "/pulls?" in p:
            return "list_pull_requests"
        if "/actions/runs/" in p and p.rstrip("/").endswith("/jobs"):
            return "list_workflow_run_jobs"
        if "/actions/runs" in p:
            return "list_workflow_runs"
        if "/readme" in p:
            return "get_readme"
        if "/contents/" in p:
            return "get_file_contents"
        if "/tags" in p:
            return "get_latest_tag"
        if p.startswith("rate_limit"):
            return "rate_limit"
        return (p.split("/")[0] if p else "unknown") or "unknown"

    @staticmethod
    def _record_api(operation: str, status: str) -> None:
        try:
            from ..observability.metrics import record_github_api_request

            record_github_api_request(operation, status)
        except Exception:
            pass

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

    async def list_repos(
        self,
        org: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """GET /user/repos or /orgs/{org}/repos"""
        per_page = max(1, min(int(per_page or 30), 100))
        org_name = (org or (self.account or {}).get("account_identifier") or "").strip()
        path = f"/orgs/{org_name}/repos" if org_name else "/user/repos"
        data = await self._get(path, params={"per_page": per_page, "sort": "updated"})
        if not isinstance(data, list):
            return []
        out: list[dict[str, Any]] = []
        for repo in data:
            if not isinstance(repo, dict):
                continue
            out.append(
                {
                    "id": repo.get("id"),
                    "name": repo.get("name"),
                    "full_name": repo.get("full_name"),
                    "private": bool(repo.get("private")),
                    "html_url": repo.get("html_url"),
                    "default_branch": repo.get("default_branch"),
                }
            )
        return out

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

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """GET /repos/{owner}/{repo}/pulls/{number}"""
        data = await self._get(f"/repos/{owner}/{repo}/pulls/{int(number)}")
        if not isinstance(data, dict):
            return {}
        return {
            "number": data.get("number"),
            "title": data.get("title"),
            "state": data.get("state"),
            "user": (data.get("user") or {}).get("login"),
            "html_url": data.get("html_url"),
            "body": (data.get("body") or "")[:2000],
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "head": ((data.get("head") or {}).get("ref")),
            "base": ((data.get("base") or {}).get("ref")),
        }

    async def list_pull_request_files(
        self, owner: str, repo: str, number: int
    ) -> list[dict[str, Any]]:
        """GET /repos/{owner}/{repo}/pulls/{number}/files"""
        data = await self._get(
            f"/repos/{owner}/{repo}/pulls/{int(number)}/files",
            params={"per_page": 100},
        )
        if not isinstance(data, list):
            return []
        return [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
                "changes": f.get("changes"),
            }
            for f in data
            if isinstance(f, dict)
        ]

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """GET /repos/{owner}/{repo} — default branch and metadata."""
        data = await self._get(f"/repos/{owner}/{repo}")
        if not isinstance(data, dict):
            return {}
        return {
            "full_name": data.get("full_name"),
            "default_branch": data.get("default_branch") or "main",
            "html_url": data.get("html_url"),
            "private": bool(data.get("private")),
        }

    async def list_workflow_runs(
        self,
        repo: str,
        status: str | None = "failure",
        per_page: int = 20,
        branch: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            params: dict[str, Any] = {"per_page": per_page}
            if status:
                params["status"] = status
            if branch:
                params["branch"] = branch
            data = await self._get(
                f"/repos/{repo}/actions/runs",
                params=params,
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
                    "head_sha": (run.get("head_sha") or "")[:7],
                    "event": run.get("event"),
                    "display_title": run.get("display_title") or run.get("name"),
                    "run_attempt": run.get("run_attempt"),
                    "actor": ((run.get("actor") or {}).get("login")),
                }
                for run in runs
                if isinstance(run, dict)
            ]
        except GitHubAPIError:
            raise
        except Exception:
            return []

    async def list_workflow_run_jobs(
        self, owner: str, repo: str, run_id: int
    ) -> list[dict[str, Any]]:
        """GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs"""
        data = await self._get(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}/jobs",
            params={"per_page": 100},
        )
        if not isinstance(data, dict):
            return []
        jobs = data.get("jobs") or []
        return [
            {
                "id": j.get("id"),
                "name": j.get("name"),
                "status": j.get("status"),
                "conclusion": j.get("conclusion"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
            }
            for j in jobs
            if isinstance(j, dict)
        ]

    async def get_workflow_run(
        self, owner: str, repo: str, run_id: int
    ) -> dict[str, Any]:
        """GET /repos/{owner}/{repo}/actions/runs/{run_id}"""
        data = await self._get(
            f"/repos/{owner}/{repo}/actions/runs/{int(run_id)}"
        )
        if not isinstance(data, dict):
            return {}
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "status": data.get("status"),
            "conclusion": data.get("conclusion"),
            "html_url": data.get("html_url"),
            "created_at": data.get("created_at"),
            "updated_at": data.get("updated_at"),
            "head_branch": data.get("head_branch"),
            "head_sha": (data.get("head_sha") or "")[:12],
            "event": data.get("event"),
            "display_title": data.get("display_title") or data.get("name"),
            "run_attempt": data.get("run_attempt"),
            "actor": ((data.get("actor") or {}).get("login")),
            "path": data.get("path"),
        }

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
            # TODO(S3-P3.1): Implement a lightweight 'ping' action for use by health probes
            if action in ("ping", "test_connection"):
                # Prefer /rate_limit — cheap auth check without mutating state.
                data = await self._get("/rate_limit")
                return {
                    "ok": True,
                    "tool": "github",
                    "action": action,
                    "result": data,
                }
        except GitHubAPIError as exc:
            # TODO(S3-P3.1): Increment health and connector metrics during probe runs and errors
            _record_connector_error(exc.error_type)
            try:
                from ..observability.logger import logger

                logger.warning(
                    "GitHub connector action failed",
                    extra={
                        "connector": "github",
                        "error_type": exc.error_type,
                        "action": action,
                    },
                )
            except Exception:
                pass
            return {
                "ok": False,
                "tool": "github",
                "action": action,
                "error": {
                    "type": exc.error_type,
                    "message": _mask_secret(exc.message, self._token()),
                },
            }
        except Exception as exc:
            _record_connector_error("network_error")
            try:
                from ..observability.logger import logger

                logger.warning(
                    "GitHub connector action failed",
                    extra={
                        "connector": "github",
                        "error_type": "network_error",
                        "action": action,
                    },
                )
            except Exception:
                pass
            return {
                "ok": False,
                "tool": "github",
                "action": action,
                "error": {
                    "type": "network_error",
                    "message": _mask_secret(str(exc), self._token()),
                },
            }
        return await super().execute_action(action, params)
