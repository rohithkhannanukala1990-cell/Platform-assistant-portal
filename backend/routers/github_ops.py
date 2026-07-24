"""Read-only GitHub operations for the authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, get_current_user
from ..connectors.github_connector import GitHubAPIError, GitHubConnector
from ..services.github_access import github_connector_for_user

router = APIRouter(prefix="/api/github", tags=["github"])


async def _github_connector_for_user(user: User) -> GitHubConnector:
    return github_connector_for_user(user)


def _http_from_github_error(exc: GitHubAPIError) -> HTTPException:
    code = 502
    if exc.error_type == "auth_failed":
        code = 401
    elif exc.error_type == "not_found":
        code = 404
    elif exc.error_type == "rate_limited":
        code = 429
    return HTTPException(status_code=code, detail=exc.message)


@router.get("/repos")
async def api_github_repos(
    org: str | None = Query(default=None),
    per_page: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    try:
        return await connector.list_repos(org=org, per_page=per_page)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/pulls")
async def api_github_pulls(
    owner: str,
    repo: str,
    state: str = Query(default="open"),
    per_page: int = Query(default=30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    full = f"{owner}/{repo}"
    try:
        return await connector.list_pull_requests(full, state=state, per_page=per_page)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/actions/runs")
async def api_github_workflow_runs(
    owner: str,
    repo: str,
    status: str | None = Query(default=None),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    full = f"{owner}/{repo}"
    try:
        return await connector.list_workflow_runs(full, status=status, per_page=per_page)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/pulls/{number}")
async def api_github_pull_detail(
    owner: str,
    repo: str,
    number: int,
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    try:
        return await connector.get_pull_request(owner, repo, number)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/pulls/{number}/files")
async def api_github_pull_files(
    owner: str,
    repo: str,
    number: int,
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    try:
        return await connector.list_pull_request_files(owner, repo, number)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/actions/runs/{run_id}")
async def api_github_workflow_run_detail(
    owner: str,
    repo: str,
    run_id: int,
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    try:
        return await connector.get_workflow_run(owner, repo, run_id)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc


@router.get("/repos/{owner}/{repo}/actions/runs/{run_id}/jobs")
async def api_github_workflow_run_jobs(
    owner: str,
    repo: str,
    run_id: int,
    current_user: User = Depends(get_current_user),
):
    connector = await _github_connector_for_user(current_user)
    try:
        return await connector.list_workflow_run_jobs(owner, repo, run_id)
    except GitHubAPIError as exc:
        raise _http_from_github_error(exc) from exc
