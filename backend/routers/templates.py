"""Admin workspace templates — reusable blueprints."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import User, get_current_user, require_admin
from ..database import (
    Template,
    TemplateApplication,
    TemplateTool,
    Tool,
    ToolAccount,
    Workspace,
    WorkspaceMember,
    WorkspaceTool,
    engine,
)

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    icon: Optional[str] = "📋"
    color: Optional[str] = "#6366f1"
    category: Optional[str] = "general"
    environment: Optional[str] = "production"
    tags: Optional[List[str]] = []
    recommended_golden_path_keys: Optional[List[str]] = []
    is_published: Optional[bool] = False


class TemplateUpdate(BaseModel):
    """Partial update for workspace templates (PUT/PATCH)."""

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: str | None = None
    environment: Optional[str] = None
    tags: Optional[List[str]] = None
    recommended_golden_path_keys: list[str] | None = None
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None


class TemplateResponse(BaseModel):
    """API shape for template payloads (list/detail/mutations)."""

    id: str
    name: str
    slug: str
    description: str = ""
    icon: str = "📋"
    color: str = "#6366f1"
    category: str | None = None
    environment: str = "production"
    tags: list[str] = []
    recommended_golden_path_keys: list[str] = []
    is_active: bool = True
    is_published: bool = False
    use_count: int = 0
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TemplateToolAdd(BaseModel):
    tool_id: str
    account_id: Optional[str] = None
    display_order: Optional[int] = 0
    is_required: Optional[bool] = True
    config_hints: Optional[dict] = Field(default_factory=dict)


class TemplateApply(BaseModel):
    workspace_name: Optional[str] = None
    environment: Optional[str] = None
    description: Optional[str] = None


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


def _normalize_category(value: str | None) -> str | None:
    if value is None:
        return None
    cat = str(value).strip()
    if not cat:
        raise HTTPException(status_code=400, detail="category must be a non-empty string")
    # TODO: enforce against a shared allowed-category registry when one exists.
    return cat


def _normalize_golden_path_keys(keys: list[str] | None) -> list[str]:
    """Basic validation for recommended golden-path keys (slugs)."""
    if keys is None:
        return []
    cleaned: list[str] = []
    for raw in keys:
        key = str(raw or "").strip()
        if not key:
            raise HTTPException(
                status_code=400,
                detail="recommended_golden_path_keys entries must be non-empty strings",
            )
        cleaned.append(key)
    # TODO: cross-check against GoldenPathTemplate.slug via a shared validator when available.
    return cleaned


def _golden_path_keys_parse(raw: str | None) -> list[str]:
    return [str(x) for x in _tags_parse(raw) if str(x).strip()]


def _golden_path_keys_dump(keys: Optional[List[str]]) -> str:
    return json.dumps(_normalize_golden_path_keys(list(keys or [])))


def slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:120] if s else "") or "template"


def _ensure_unique_template_slug(session: Session, base_slug: str, exclude_id: Optional[str] = None) -> str:
    slug = base_slug
    n = 2
    while True:
        q = select(Template).where(Template.slug == slug)
        row = session.exec(q).first()
        if not row or (exclude_id and row.id == exclude_id):
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _ensure_unique_workspace_slug(session: Session, base_slug: str, exclude_id: Optional[str] = None) -> str:
    slug = base_slug
    n = 2
    while True:
        q = select(Workspace).where(Workspace.slug == slug)
        row = session.exec(q).first()
        if not row or (exclude_id and row.id == exclude_id):
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _template_base_dict(t: Template) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "description": t.description or "",
        "icon": t.icon,
        "color": t.color,
        "category": t.category,
        "environment": t.environment,
        "tags": _tags_parse(t.tags),
        "recommended_golden_path_keys": _golden_path_keys_parse(
            getattr(t, "recommended_golden_path_keys", None)
        ),
        "is_active": bool(t.is_active),
        "is_published": bool(t.is_published),
        "use_count": t.use_count,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


def _serialize_template_tool(session: Session, tt: TemplateTool) -> dict[str, Any]:
    tool = session.get(Tool, tt.tool_id)
    return {
        "id": tt.id,
        "template_id": tt.template_id,
        "tool_id": tt.tool_id,
        "account_id": tt.account_id,
        "display_order": tt.display_order,
        "is_required": bool(tt.is_required),
        "config_hints": json.loads(tt.config_hints) if tt.config_hints else {},
        "tool_name": tool.name if tool else tt.tool_id,
        "tool_icon": tool.icon if tool else None,
        "tool_category": tool.category if tool else None,
    }


def _template_tool_rows_ordered(session: Session, template_id: str) -> list[TemplateTool]:
    return session.exec(
        select(TemplateTool)
        .where(TemplateTool.template_id == template_id)
        .order_by(TemplateTool.display_order.asc(), TemplateTool.id.asc())
    ).all()


def _template_has_tool(session: Session, template_id: str, tool_id: str) -> bool:
    q = select(TemplateTool).where(
        TemplateTool.template_id == template_id,
        TemplateTool.tool_id == tool_id,
    )
    return session.exec(q).first() is not None


def _serialize_workspace_tool(session: Session, wt: WorkspaceTool) -> dict[str, Any]:
    tool = session.get(Tool, wt.tool_id)
    acc_row = session.get(ToolAccount, wt.account_id) if wt.account_id else None
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
        "account_name": acc_row.account_name if acc_row else None,
        "account_environment": acc_row.environment if acc_row else None,
        "account_status": acc_row.status if acc_row else None,
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


def _workspace_tool_rows_ordered(session: Session, workspace_id: str) -> list[WorkspaceTool]:
    return session.exec(
        select(WorkspaceTool)
        .where(WorkspaceTool.workspace_id == workspace_id)
        .order_by(WorkspaceTool.display_order.asc(), WorkspaceTool.added_at.asc())
    ).all()


def _full_workspace(session: Session, workspace_id: str) -> dict[str, Any]:
    w = session.get(Workspace, workspace_id)
    if not w or not w.is_active:
        raise HTTPException(status_code=404, detail="Workspace not found")
    members = session.exec(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    ).all()
    tools = [_serialize_workspace_tool(session, wt) for wt in _workspace_tool_rows_ordered(session, workspace_id)]
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


@router.get("/categories")
def list_template_categories(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(select(Template).where(Template.is_active == 1)).all()
        counts: dict[str, int] = {}
        for t in rows:
            counts[t.category] = counts.get(t.category, 0) + 1
        return [{"category": k, "count": v} for k, v in sorted(counts.items())]


@router.get("")
def list_templates(
    category: Optional[str] = Query(None),
    published: Optional[bool] = Query(None),
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        q = select(Template).where(Template.is_active == 1)
        if category:
            q = q.where(Template.category == category.strip())
        if published is True:
            q = q.where(Template.is_published == 1)
        elif published is False:
            q = q.where(Template.is_published == 0)
        q = q.order_by(Template.use_count.desc(), Template.created_at.desc())
        rows = session.exec(q).all()
        out: list[dict[str, Any]] = []
        for t in rows:
            tts = session.exec(
                select(TemplateTool).where(TemplateTool.template_id == t.id)
            ).all()
            tool_count = len(tts)
            wtools = session.exec(
                select(TemplateTool, Tool)
                .join(Tool, TemplateTool.tool_id == Tool.id)
                .where(TemplateTool.template_id == t.id)
                .order_by(TemplateTool.display_order.asc(), TemplateTool.id.asc())
                .limit(5)
            ).all()
            preview = [{"tool_id": tt.tool_id, "name": tl.name, "icon": tl.icon} for tt, tl in wtools]
            d = _template_base_dict(t)
            d["tool_count"] = tool_count
            d["tools_preview"] = preview
            out.append(d)
        return out


@router.get("/{template_id}/applications")
def list_template_applications(
    template_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t or not t.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        apps = session.exec(
            select(TemplateApplication)
            .where(TemplateApplication.template_id == template_id)
            .order_by(TemplateApplication.applied_at.desc())
            .limit(20)
        ).all()
        out = []
        for a in apps:
            ws = session.get(Workspace, a.workspace_id)
            out.append(
                {
                    "workspace_id": a.workspace_id,
                    "workspace_name": ws.name if ws else "(deleted)",
                    "applied_by": a.applied_by,
                    "applied_at": a.applied_at.isoformat(),
                }
            )
        return out


@router.get("/{template_id}")
def get_template(template_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t or not t.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        tools = [_serialize_template_tool(session, tt) for tt in _template_tool_rows_ordered(session, template_id)]
        payload = _template_base_dict(t)
        payload["tools"] = tools
        return payload


@router.post("")
def create_template(body: TemplateCreate, admin: User = Depends(require_admin)):
    tid = f"tmpl-{uuid.uuid4().hex[:8]}"
    base_slug = slugify(body.name)
    now = _now()
    with Session(engine) as session:
        slug = _ensure_unique_template_slug(session, base_slug)
        category = _normalize_category(body.category or "general") or "general"
        row = Template(
            id=tid,
            name=body.name.strip(),
            slug=slug,
            description=(body.description or "").strip() or None,
            icon=body.icon or "📋",
            color=body.color or "#6366f1",
            category=category,
            environment=(body.environment or "production").strip(),
            tags=_tags_dump(body.tags),
            recommended_golden_path_keys=_golden_path_keys_dump(
                body.recommended_golden_path_keys
            ),
            is_active=1,
            is_published=1 if body.is_published else 0,
            use_count=0,
            created_by=admin.username,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _template_base_dict(row)


def _apply_template_update(session: Session, t: Template, data: dict[str, Any]) -> Template:
    if "name" in data and data["name"] is not None:
        t.name = str(data["name"]).strip()
        t.slug = _ensure_unique_template_slug(session, slugify(t.name), exclude_id=t.id)
    if "description" in data:
        t.description = (
            str(data["description"]).strip() if data["description"] is not None else None
        )
    if "icon" in data and data["icon"] is not None:
        t.icon = data["icon"]
    if "color" in data and data["color"] is not None:
        t.color = data["color"]
    if "category" in data and data["category"] is not None:
        t.category = _normalize_category(data["category"]) or t.category
    if "environment" in data and data["environment"] is not None:
        t.environment = str(data["environment"]).strip()
    if "tags" in data and data["tags"] is not None:
        t.tags = _tags_dump(data["tags"])
    if "recommended_golden_path_keys" in data and data["recommended_golden_path_keys"] is not None:
        t.recommended_golden_path_keys = _golden_path_keys_dump(
            data["recommended_golden_path_keys"]
        )
    if "is_published" in data and data["is_published"] is not None:
        t.is_published = 1 if data["is_published"] else 0
    if "is_active" in data and data["is_active"] is not None:
        t.is_active = 1 if data["is_active"] else 0
    t.updated_at = _now()
    session.add(t)
    session.commit()
    session.refresh(t)
    return t


@router.put("/{template_id}")
def update_template(
    template_id: str,
    body: TemplateUpdate,
    _admin: User = Depends(require_admin),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        t = _apply_template_update(session, t, data)
        return _template_base_dict(t)


@router.patch("/{template_id}")
def patch_template(
    template_id: str,
    body: TemplateUpdate,
    _admin: User = Depends(require_admin),
):
    """Partial update — category / recommended golden paths (Admin / PlatformAdmin)."""
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        t = _apply_template_update(session, t, data)
        return _template_base_dict(t)


@router.delete("/{template_id}")
def soft_delete_template(template_id: str, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        t.is_active = 0
        t.updated_at = _now()
        session.add(t)
        session.commit()
        return {"deleted": True}


@router.post("/{template_id}/tools")
def add_template_tool(
    template_id: str,
    body: TemplateToolAdd,
    _admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t or not t.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        tool = session.get(Tool, body.tool_id.strip())
        if not tool:
            raise HTTPException(status_code=404, detail="Unknown tool_id")
        aid = (body.account_id or "").strip() or None
        if aid:
            acc = session.get(ToolAccount, aid)
            if not acc or acc.tool_id != tool.id:
                raise HTTPException(status_code=400, detail="account_id does not match tool_id")
        if _template_has_tool(session, template_id, tool.id):
            return {
                "already_exists": True,
                "tools": [_serialize_template_tool(session, x) for x in _template_tool_rows_ordered(session, template_id)],
            }
        row = TemplateTool(
            id=str(uuid.uuid4()),
            template_id=template_id,
            tool_id=tool.id,
            account_id=aid,
            display_order=body.display_order or 0,
            is_required=1 if body.is_required else 0,
            config_hints=json.dumps(body.config_hints or {}),
        )
        session.add(row)
        t.updated_at = _now()
        session.add(t)
        session.commit()
        return [_serialize_template_tool(session, x) for x in _template_tool_rows_ordered(session, template_id)]


@router.delete("/{template_id}/tools/{tool_id}")
def remove_template_tool(
    template_id: str,
    tool_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        rows = session.exec(
            select(TemplateTool).where(
                TemplateTool.template_id == template_id,
                TemplateTool.tool_id == tool_id,
            )
        ).all()
        if not rows:
            raise HTTPException(status_code=404, detail="Tool not on template")
        for r in rows:
            session.delete(r)
        t.updated_at = _now()
        session.add(t)
        session.commit()
        return {"removed": True}


@router.post("/{template_id}/apply")
def apply_template(
    template_id: str,
    body: TemplateApply,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t or not t.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        if not t.is_published and current_user.role != "Admin":
            raise HTTPException(status_code=403, detail="Template is not published")

        ws_name = (body.workspace_name or "").strip() or f"{t.name} Workspace"
        env = (body.environment or t.environment or "production").strip()
        desc = (body.description or "").strip() or f"Created from template: {t.name}"

        wid = f"ws-{uuid.uuid4().hex[:8]}"
        base_slug = slugify(ws_name) + "-" + uuid.uuid4().hex[:4]
        slug = _ensure_unique_workspace_slug(session, base_slug)
        now = _now()

        ws = Workspace(
            id=wid,
            name=ws_name,
            slug=slug,
            description=desc,
            icon=t.icon,
            color=t.color,
            environment=env,
            tags=t.tags,
            is_active=1,
            is_pinned=0,
            created_by=current_user.username,
            created_at=now,
            updated_at=now,
        )
        session.add(ws)

        template_tools = _template_tool_rows_ordered(session, template_id)
        n_added = 0
        for tt in template_tools:
            session.add(
                WorkspaceTool(
                    id=str(uuid.uuid4()),
                    workspace_id=wid,
                    tool_id=tt.tool_id,
                    account_id=tt.account_id,
                    display_order=tt.display_order,
                    is_primary=0,
                    added_at=now,
                )
            )
            n_added += 1

        app_row = TemplateApplication(
            id=f"tap-{uuid.uuid4().hex[:10]}",
            template_id=template_id,
            workspace_id=wid,
            applied_by=current_user.username,
            applied_at=now,
        )
        session.add(app_row)

        t.use_count = (t.use_count or 0) + 1
        t.updated_at = now
        session.add(t)

        session.commit()

        workspace_payload = _full_workspace(session, wid)
        return {
            "workspace": workspace_payload,
            "tools_added": n_added,
            "template_name": t.name,
        }


@router.post("/{template_id}/duplicate")
def duplicate_template(template_id: str, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        t = session.get(Template, template_id)
        if not t or not t.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        new_name = f"{t.name} (Copy)"
        new_id = f"tmpl-{uuid.uuid4().hex[:8]}"
        base_slug = slugify(new_name) + "-copy"
        slug = _ensure_unique_template_slug(session, base_slug)
        now = _now()
        copy = Template(
            id=new_id,
            name=new_name,
            slug=slug,
            description=t.description,
            icon=t.icon,
            color=t.color,
            category=t.category,
            environment=t.environment,
            tags=t.tags,
            recommended_golden_path_keys=getattr(t, "recommended_golden_path_keys", None) or "[]",
            is_active=1,
            is_published=0,
            use_count=0,
            created_by=_admin.username,
            created_at=now,
            updated_at=now,
        )
        session.add(copy)
        for tt in _template_tool_rows_ordered(session, template_id):
            session.add(
                TemplateTool(
                    id=str(uuid.uuid4()),
                    template_id=new_id,
                    tool_id=tt.tool_id,
                    account_id=tt.account_id,
                    display_order=tt.display_order,
                    is_required=tt.is_required,
                    config_hints=tt.config_hints or "{}",
                )
            )
        session.commit()
        session.refresh(copy)
        return _template_base_dict(copy)
