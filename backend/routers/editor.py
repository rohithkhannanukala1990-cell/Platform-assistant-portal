"""Code editor API — persistence, GitHub browse, PR proposals, agent actions."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ..auth import User, get_current_user, require_admin, write_audit
from ..services.editor_service import (
    GITHUB_NOT_CONNECTED,
    create_file,
    delete_file,
    format_content,
    fulfill_editor_pr_approval,
    list_files,
    parse_github_repo_url,
    propose_pr,
    require_github,
    run_editor_agent_action,
    serialize_file,
    update_file,
    validate_content,
)
from ..services.isolation import require_tenant
from ..db.core import engine
from sqlmodel import Session

from ..db.models.editor import EditorFile
from ..services.editor_service import get_owned_file

router = APIRouter(prefix="/api/editor", tags=["editor"])


class FileCreateBody(BaseModel):
    filename: str = "untitled.yaml"
    content: str = ""
    language: Optional[str] = None
    workspace_id: Optional[str] = None
    source_type: str = "scratch"
    source_repo: Optional[str] = None
    source_path: Optional[str] = None
    source_ref: Optional[str] = None
    source_sha: Optional[str] = None


class FileUpdateBody(BaseModel):
    content: Optional[str] = None
    filename: Optional[str] = None
    language: Optional[str] = None


class ProposePRBody(BaseModel):
    title: str
    body: str = ""
    branch_name: str = ""
    base_branch: str = "main"
    force: bool = False


class AgentActionBody(BaseModel):
    agent: Optional[str] = None
    action: Optional[str] = None
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    instruction: Optional[str] = None


@router.get("/files")
def api_list_files(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    return list_files(tenant_id=tenant_id, username=current_user.username)


@router.post("/files", status_code=201)
def api_create_file(
    request: Request,
    body: FileCreateBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return create_file(
        tenant_id=tenant_id,
        username=current_user.username,
        filename=body.filename,
        content=body.content,
        language=body.language,
        workspace_id=body.workspace_id,
        source_type=body.source_type,
        source_repo=body.source_repo,
        source_path=body.source_path,
        source_ref=body.source_ref,
        source_sha=body.source_sha,
    )


@router.get("/files/{file_id}")
def api_get_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = get_owned_file(
            session, file_id, tenant_id=tenant_id, username=current_user.username
        )
        return serialize_file(row)


@router.put("/files/{file_id}")
def api_update_file(
    request: Request,
    file_id: str,
    body: FileUpdateBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return update_file(
        file_id=file_id,
        tenant_id=tenant_id,
        username=current_user.username,
        content=body.content,
        filename=body.filename,
        language=body.language,
    )


@router.delete("/files/{file_id}", status_code=204)
def api_delete_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    delete_file(file_id=file_id, tenant_id=tenant_id, username=current_user.username)
    return None


@router.post("/files/{file_id}/format")
def api_format_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = get_owned_file(
            session, file_id, tenant_id=tenant_id, username=current_user.username
        )
        result = format_content(row.language, row.content)
    if result.get("ok") and result.get("content") is not None:
        updated = update_file(
            file_id=file_id,
            tenant_id=tenant_id,
            username=current_user.username,
            content=result["content"],
        )
        return {"ok": True, "file": updated}
    return result


@router.post("/files/{file_id}/validate")
def api_validate_file(
    request: Request,
    file_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = get_owned_file(
            session, file_id, tenant_id=tenant_id, username=current_user.username
        )
        return validate_content(row.language, row.content)


@router.get("/github/tree")
async def api_github_tree(
    request: Request,
    repo: str = Query(...),
    ref: str = Query("main"),
    path: str = Query(""),
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    conn = require_github(current_user, tenant_id)
    try:
        entries = await conn.list_tree(repo, ref=ref, path=path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"repo": repo, "ref": ref, "path": path, "entries": entries}


@router.get("/github/file")
async def api_github_file(
    request: Request,
    repo: str = Query(...),
    ref: str = Query("main"),
    path: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    conn = require_github(current_user, tenant_id)
    try:
        meta = await conn.get_file_meta(repo, path, ref=ref)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Persist as owned editor file
    from ..services.editor_service import detect_language

    name = path.rsplit("/", 1)[-1]
    created = create_file(
        tenant_id=tenant_id,
        username=current_user.username,
        filename=name,
        content=meta.get("content") or "",
        language=detect_language(name),
        source_type="github",
        source_repo=repo,
        source_path=path,
        source_ref=ref,
        source_sha=meta.get("sha"),
    )
    return {"file": created, "meta": {"sha": meta.get("sha"), "html_url": meta.get("html_url")}}


@router.post("/files/{file_id}/propose-pr")
async def api_propose_pr(
    request: Request,
    file_id: str,
    body: ProposePRBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return await propose_pr(
        file_id=file_id,
        tenant_id=tenant_id,
        user=current_user,
        title=body.title,
        body=body.body,
        branch_name=body.branch_name,
        base_branch=body.base_branch,
        force=body.force,
    )


@router.post("/pr-approvals/{approval_id}/approve")
async def api_approve_editor_pr(
    request: Request,
    approval_id: str,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    return await fulfill_editor_pr_approval(
        approval_id=approval_id,
        tenant_id=tenant_id,
        decided_by=admin.username,
        user=admin,
    )


@router.post("/files/{file_id}/agent-action")
async def api_agent_action(
    request: Request,
    file_id: str,
    body: AgentActionBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return await run_editor_agent_action(
        file_id=file_id,
        tenant_id=tenant_id,
        user=current_user,
        agent=body.agent,
        action=body.action,
        selection_start=body.selection_start,
        selection_end=body.selection_end,
        instruction=body.instruction,
    )


@router.get("/templates")
def api_list_templates(request: Request, current_user: User = Depends(get_current_user)):
    """List golden path templates usable as new-file starters."""
    _ = require_tenant(request)
    try:
        from ..routers.golden_paths import GoldenPathTemplate

        with Session(engine) as session:
            rows = session.exec(
                select(GoldenPathTemplate).where(GoldenPathTemplate.is_active == True)  # noqa: E712
            ).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "category": getattr(r, "category", None),
                    "description": getattr(r, "description", None) or "",
                }
                for r in rows
            ]
    except Exception:
        return []


# Fix missing import for select in templates
from sqlmodel import select  # noqa: E402
