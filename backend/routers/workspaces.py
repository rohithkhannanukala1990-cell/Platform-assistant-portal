"""Workspace API — saved tool + account groupings."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import User, get_current_user
from ..database import (
    Tool,
    ToolAccount,
    ToolConnectionLog,
    Workspace,
    WorkspaceMember,
    WorkspaceTool,
    engine,
)

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "🗂️"
    color: Optional[str] = "#6366f1"
    environment: Optional[str] = "production"
    tags: Optional[List[str]] = []
    is_pinned: Optional[bool] = False


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    environment: Optional[str] = None
    tags: Optional[List[str]] = None
    is_pinned: Optional[bool] = None
    is_active: Optional[bool] = None


class WorkspaceToolAdd(BaseModel):
    tool_id: str
    account_id: Optional[str] = None
    display_order: Optional[int] = 0
    is_primary: Optional[bool] = False


class WorkspaceToolsReorderBody(BaseModel):
    """Ordered list of `workspace_tools.id` row IDs (display_order set by index)."""

    tool_ids: List[str] = Field(..., description="Ordered workspace_tools row IDs")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tags_parse(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _tags_dump(tags: Optional[List[str]]) -> str:
    return json.dumps(list(tags or []))


def slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:120] if s else "") or "workspace"


def _ensure_unique_slug(session: Session, base_slug: str, exclude_id: Optional[str] = None) -> str:
    slug = base_slug
    n = 2
    while True:
        q = select(Workspace).where(Workspace.slug == slug)
        row = session.exec(q).first()
        if not row or (exclude_id and row.id == exclude_id):
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _workspace_tool_exists(
    session: Session,
    workspace_id: str,
    tool_id: str,
    account_id: Optional[str],
) -> bool:
    q = select(WorkspaceTool).where(
        WorkspaceTool.workspace_id == workspace_id,
        WorkspaceTool.tool_id == tool_id,
    )
    if account_id is None:
        q = q.where(WorkspaceTool.account_id.is_(None))  # type: ignore[union-attr]
    else:
        q = q.where(WorkspaceTool.account_id == account_id)
    return session.exec(q).first() is not None


def _latest_log(session: Session, account_id: str) -> ToolConnectionLog | None:
    return session.exec(
        select(ToolConnectionLog)
        .where(ToolConnectionLog.account_id == account_id)
        .order_by(ToolConnectionLog.tested_at.desc())
    ).first()


def _resolve_account(session: Session, tool_id: str, account_id: Optional[str]) -> ToolAccount | None:
    if account_id:
        acc = session.get(ToolAccount, account_id)
        if acc and acc.tool_id == tool_id and acc.is_active == 1:
            return acc
    return session.exec(
        select(ToolAccount)
        .where(ToolAccount.tool_id == tool_id, ToolAccount.is_active == 1)
        .order_by(ToolAccount.created_at.desc())
    ).first()


def _tool_rows_ordered(session: Session, workspace_id: str) -> list[WorkspaceTool]:
    return session.exec(
        select(WorkspaceTool)
        .where(WorkspaceTool.workspace_id == workspace_id)
        .order_by(WorkspaceTool.display_order.asc(), WorkspaceTool.added_at.asc())
    ).all()


def _serialize_tool_entry(session: Session, wt: WorkspaceTool) -> dict[str, Any]:
    tool = session.get(Tool, wt.tool_id)
    acc = session.get(ToolAccount, wt.account_id) if wt.account_id else None
    return {
        "id": wt.id,
        "workspace_id": wt.workspace_id,
        "tool_id": wt.tool_id,
        "account_id": wt.account_id,
        "display_order": wt.display_order,
        "is_primary": bool(wt.is_primary),
        "added_at": wt.added_at.isoformat(),
        "tool_name": tool.name if tool else wt.tool_id,
        "tool_icon": tool.icon if tool else None,
        "tool_category": tool.category if tool else None,
        "account_name": acc.account_name if acc else None,
        "account_environment": acc.environment if acc else None,
        "account_status": acc.status if acc else None,
    }


def _workspace_base_dict(w: Workspace) -> dict[str, Any]:
    return {
        "id": w.id,
        "name": w.name,
        "slug": w.slug,
        "description": w.description or "",
        "icon": w.icon,
        "color": w.color,
        "environment": w.environment,
        "tags": _tags_parse(w.tags),
        "is_active": bool(w.is_active),
        "is_pinned": bool(w.is_pinned),
        "created_by": w.created_by,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }


@router.get("")
def list_workspaces(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(
            select(Workspace)
            .where(Workspace.is_active == 1)
            .order_by(Workspace.is_pinned.desc(), Workspace.created_at.desc())
        ).all()
        out: list[dict[str, Any]] = []
        for w in rows:
            wts = session.exec(
                select(WorkspaceTool).where(WorkspaceTool.workspace_id == w.id)
            ).all()
            tool_count = len(wts)
            mems = session.exec(
                select(WorkspaceMember).where(WorkspaceMember.workspace_id == w.id)
            ).all()
            member_count = len(mems)
            wtools = session.exec(
                select(WorkspaceTool, Tool)
                .join(Tool, WorkspaceTool.tool_id == Tool.id)
                .where(WorkspaceTool.workspace_id == w.id)
                .order_by(WorkspaceTool.display_order.asc(), WorkspaceTool.added_at.asc())
                .limit(5)
            ).all()
            preview = []
            for wt, t in wtools:
                preview.append({"tool_id": wt.tool_id, "name": t.name, "icon": t.icon})
            d = _workspace_base_dict(w)
            d["tool_count"] = tool_count
            d["member_count"] = member_count
            d["tools_preview"] = preview
            out.append(d)
        return out


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w or not w.is_active:
            raise HTTPException(status_code=404, detail="Workspace not found")
        members = session.exec(
            select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        ).all()
        tools = [_serialize_tool_entry(session, wt) for wt in _tool_rows_ordered(session, workspace_id)]
        payload = _workspace_base_dict(w)
        payload["tools"] = tools
        payload["members"] = [
            {
                "id": m.id,
                "user_id": m.user_id,
                "role": m.role,
                "added_at": m.added_at.isoformat(),
            }
            for m in members
        ]
        payload["last_used_at"] = None
        return payload


@router.post("")
def create_workspace(body: WorkspaceCreate, current_user: User = Depends(get_current_user)):
    wid = f"ws-{uuid.uuid4().hex[:8]}"
    base_slug = slugify(body.name)
    now = _now()
    with Session(engine) as session:
        slug = _ensure_unique_slug(session, base_slug)
        row = Workspace(
            id=wid,
            name=body.name.strip(),
            slug=slug,
            description=(body.description or "").strip() or None,
            icon=body.icon or "🗂️",
            color=body.color or "#6366f1",
            environment=(body.environment or "production").strip(),
            tags=_tags_dump(body.tags),
            is_active=1,
            is_pinned=1 if body.is_pinned else 0,
            created_by=current_user.username,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _workspace_base_dict(row)


@router.put("/{workspace_id}")
def update_workspace(
    workspace_id: str,
    body: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w:
            raise HTTPException(status_code=404, detail="Workspace not found")
        if "name" in data and data["name"] is not None:
            w.name = str(data["name"]).strip()
            if "slug" not in data:
                w.slug = _ensure_unique_slug(session, slugify(w.name), exclude_id=w.id)
        if "description" in data:
            w.description = (
                str(data["description"]).strip() if data["description"] is not None else None
            )
        if "icon" in data and data["icon"] is not None:
            w.icon = data["icon"]
        if "color" in data and data["color"] is not None:
            w.color = data["color"]
        if "environment" in data and data["environment"] is not None:
            w.environment = str(data["environment"]).strip()
        if "tags" in data and data["tags"] is not None:
            w.tags = _tags_dump(data["tags"])
        if "is_pinned" in data and data["is_pinned"] is not None:
            w.is_pinned = 1 if data["is_pinned"] else 0
        if "is_active" in data and data["is_active"] is not None:
            w.is_active = 1 if data["is_active"] else 0
        w.updated_at = _now()
        session.add(w)
        session.commit()
        session.refresh(w)
        return _workspace_base_dict(w)


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w:
            raise HTTPException(status_code=404, detail="Workspace not found")
        w.is_active = 0
        w.updated_at = _now()
        session.add(w)
        for wt in session.exec(
            select(WorkspaceTool).where(WorkspaceTool.workspace_id == workspace_id)
        ).all():
            session.delete(wt)
        session.commit()
        return {"deleted": True}


@router.post("/{workspace_id}/tools")
def add_workspace_tool(
    workspace_id: str,
    body: WorkspaceToolAdd,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w or not w.is_active:
            raise HTTPException(status_code=404, detail="Workspace not found")
        tool = session.get(Tool, body.tool_id.strip())
        if not tool:
            raise HTTPException(status_code=404, detail="Unknown tool_id")
        aid = (body.account_id or "").strip() or None
        if aid:
            acc = session.get(ToolAccount, aid)
            if not acc or acc.tool_id != tool.id:
                raise HTTPException(status_code=400, detail="account_id does not match tool_id")
        if _workspace_tool_exists(session, workspace_id, tool.id, aid):
            return {"already_exists": True, "tools": [_serialize_tool_entry(session, x) for x in _tool_rows_ordered(session, workspace_id)]}
        row = WorkspaceTool(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            tool_id=tool.id,
            account_id=aid,
            display_order=int(body.display_order or 0),
            is_primary=1 if body.is_primary else 0,
            added_at=_now(),
        )
        session.add(row)
        session.commit()
        tools = [_serialize_tool_entry(session, x) for x in _tool_rows_ordered(session, workspace_id)]
        return {"already_exists": False, "tools": tools}


@router.delete("/{workspace_id}/tools/{tool_id}")
def remove_workspace_tool(
    workspace_id: str,
    tool_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w:
            raise HTTPException(status_code=404, detail="Workspace not found")
        rows = session.exec(
            select(WorkspaceTool).where(
                WorkspaceTool.workspace_id == workspace_id,
                WorkspaceTool.tool_id == tool_id,
            )
        ).all()
        if not rows:
            raise HTTPException(status_code=404, detail="Tool not in workspace")
        for r in rows:
            session.delete(r)
        session.commit()
        return {"removed": True}


@router.post("/{workspace_id}/tools/reorder")
def reorder_workspace_tools(
    workspace_id: str,
    body: WorkspaceToolsReorderBody,
    current_user: User = Depends(get_current_user),
):
    """`tool_ids` = ordered list of `workspace_tools.id` values."""
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w or not w.is_active:
            raise HTTPException(status_code=404, detail="Workspace not found")
        ids_ordered = body.tool_ids
        for order, wt_id in enumerate(ids_ordered):
            wt = session.get(WorkspaceTool, wt_id)
            if not wt or wt.workspace_id != workspace_id:
                raise HTTPException(status_code=400, detail=f"Invalid workspace tool id: {wt_id}")
            wt.display_order = order
            session.add(wt)
        session.commit()
        tools = [_serialize_tool_entry(session, x) for x in _tool_rows_ordered(session, workspace_id)]
        return {"tools": tools}


@router.get("/{workspace_id}/health")
def workspace_health(workspace_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w or not w.is_active:
            raise HTTPException(status_code=404, detail="Workspace not found")
        tool_statuses: list[dict[str, Any]] = []
        for wt in _tool_rows_ordered(session, workspace_id):
            tool = session.get(Tool, wt.tool_id)
            acc = _resolve_account(session, wt.tool_id, wt.account_id)
            status = acc.status if acc else "unknown"
            account_name = acc.account_name if acc else None
            last_checked = None
            if acc:
                log = _latest_log(session, acc.id)
                if log:
                    last_checked = log.tested_at.isoformat()
            tool_statuses.append(
                {
                    "tool_id": wt.tool_id,
                    "tool_name": tool.name if tool else wt.tool_id,
                    "account_name": account_name,
                    "status": status,
                    "last_checked": last_checked,
                }
            )
        total = len(tool_statuses)
        if total == 0:
            overall = "unknown"
        else:
            statuses = [t["status"] for t in tool_statuses]
            if all(s == "connected" for s in statuses):
                overall = "healthy"
            elif any(s == "failed" for s in statuses):
                overall = "critical"
            elif any(s == "connected" for s in statuses):
                overall = "degraded"
            else:
                overall = "unknown"
        healthy_count = sum(1 for t in tool_statuses if t["status"] == "connected")
        return {
            "workspace_id": workspace_id,
            "overall_status": overall,
            "tool_statuses": tool_statuses,
            "healthy_count": healthy_count,
            "total_count": total,
        }


@router.post("/{workspace_id}/duplicate")
def duplicate_workspace(workspace_id: str, current_user: User = Depends(get_current_user)):
    now = _now()
    with Session(engine) as session:
        w = session.get(Workspace, workspace_id)
        if not w or not w.is_active:
            raise HTTPException(status_code=404, detail="Workspace not found")
        new_name = f"{w.name} (Copy)"
        new_id = f"ws-{uuid.uuid4().hex[:8]}"
        base_slug = slugify(new_name)
        slug = _ensure_unique_slug(session, base_slug)
        clone = Workspace(
            id=new_id,
            name=new_name,
            slug=slug,
            description=w.description,
            icon=w.icon,
            color=w.color,
            environment=w.environment,
            tags=w.tags,
            is_active=1,
            is_pinned=0,
            created_by=current_user.username,
            created_at=now,
            updated_at=now,
        )
        session.add(clone)
        session.flush()
        for wt in _tool_rows_ordered(session, workspace_id):
            session.add(
                WorkspaceTool(
                    id=str(uuid.uuid4()),
                    workspace_id=new_id,
                    tool_id=wt.tool_id,
                    account_id=wt.account_id,
                    display_order=wt.display_order,
                    is_primary=wt.is_primary,
                    added_at=now,
                )
            )
        session.commit()
        session.refresh(clone)
        return _workspace_base_dict(clone)
