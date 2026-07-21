"""RBAC API — roles, permissions, user assignments, and authorization checks."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import User, get_current_user, require_admin
from ..database import (
    Permission,
    Role,
    RolePermission,
    UserRole,
    engine,
)
from ..rbac_core import check_user_permission, collect_all_grants_for_user

router = APIRouter(prefix="/api/rbac", tags=["rbac"])

# Capabilities used by platform-content and entity-operation routes.
VIEW_TEMPLATES = "templates:read"
VIEW_GOLDEN_PATHS = "golden_paths:read"
VIEW_SERVICE_HEALTH = "health:read"
TRIGGER_ENTITY_ACTION = "entity_actions:trigger"

ALL_PLATFORM_CAPABILITIES = frozenset(
    {
        VIEW_TEMPLATES,
        VIEW_GOLDEN_PATHS,
        VIEW_SERVICE_HEALTH,
        TRIGGER_ENTITY_ACTION,
    }
)

# Legacy auth roles are mapped explicitly while database-backed RBAC remains
# available for custom/global role assignments.
ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    "admin": ALL_PLATFORM_CAPABILITIES,
    "superadmin": ALL_PLATFORM_CAPABILITIES,
    "super admin": ALL_PLATFORM_CAPABILITIES,
    "platformadmin": ALL_PLATFORM_CAPABILITIES,
    "platform admin": ALL_PLATFORM_CAPABILITIES,
    "platformengineer": ALL_PLATFORM_CAPABILITIES,
    "platform engineer": ALL_PLATFORM_CAPABILITIES,
    "developer": ALL_PLATFORM_CAPABILITIES,
    "operator": ALL_PLATFORM_CAPABILITIES,
    # Preserve existing User behavior while making the grant explicit.
    "user": ALL_PLATFORM_CAPABILITIES,
    "viewer": frozenset(
        {VIEW_TEMPLATES, VIEW_GOLDEN_PATHS, VIEW_SERVICE_HEALTH}
    ),
    "readonly": frozenset(
        {VIEW_TEMPLATES, VIEW_GOLDEN_PATHS, VIEW_SERVICE_HEALTH}
    ),
    "read only": frozenset(
        {VIEW_TEMPLATES, VIEW_GOLDEN_PATHS, VIEW_SERVICE_HEALTH}
    ),
}


def require_capability(capability: str):
    """FastAPI dependency supporting legacy roles and global RBAC grants."""
    if ":" not in capability:
        raise ValueError(f"Invalid capability: {capability}")
    resource, action = capability.split(":", 1)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        role_key = (current_user.role or "").strip().lower()
        # Administrative legacy roles remain unconditional break-glass roles.
        if role_key in {
            "admin",
            "superadmin",
            "super admin",
            "platformadmin",
            "platform admin",
        }:
            return current_user

        with Session(engine) as session:
            assignments = session.exec(
                select(UserRole).where(UserRole.user_id == current_user.username)
            ).all()
            allowed, _reason = check_user_permission(
                session,
                current_user.username,
                resource,
                action,
                "global",
                None,
            )
        if allowed:
            return current_user

        # Explicit database assignments take precedence over broad legacy
        # defaults, including when the assignment is scoped and cannot grant
        # this global request.
        if assignments:
            raise HTTPException(status_code=403, detail="Forbidden")

        if capability in ROLE_CAPABILITIES.get(role_key, frozenset()):
            return current_user
        raise HTTPException(status_code=403, detail="Forbidden")

    return dependency


class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    permissions: Optional[List[str]] = Field(default_factory=list)


class UserRoleAssign(BaseModel):
    user_id: str
    role_id: str
    scope_type: Optional[str] = "global"
    scope_id: Optional[str] = None


class PermissionCheckBody(BaseModel):
    user_id: str
    resource: str
    action: str
    scope_type: str = "global"
    scope_id: Optional[str] = None


def slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:120] if s else "") or "role"


def _ensure_unique_role_slug(session: Session, base_slug: str, exclude_id: Optional[str] = None) -> str:
    slug = base_slug
    n = 2
    while True:
        row = session.exec(select(Role).where(Role.slug == slug)).first()
        if not row or (exclude_id and row.id == exclude_id):
            return slug
        slug = f"{base_slug}-{n}"
        n += 1


def _parse_perm_strings(session: Session, keys: list[str]) -> list[str]:
    """Validate list of 'resource:action' strings; return permission ids."""
    out: list[str] = []
    for raw in keys or []:
        if ":" not in raw:
            raise HTTPException(status_code=400, detail=f"Invalid permission key: {raw}")
        resource, action = raw.split(":", 1)
        resource = resource.strip()
        action = action.strip()
        pid = f"perm-{resource}-{action}"
        p = session.get(Permission, pid)
        if not p:
            raise HTTPException(status_code=400, detail=f"Unknown permission: {raw}")
        out.append(p.id)
    return out


def _replace_role_permissions(session: Session, role_id: str, permission_ids: list[str]) -> None:
    for rp in session.exec(select(RolePermission).where(RolePermission.role_id == role_id)).all():
        session.delete(rp)
    for pid in permission_ids:
        session.add(
            RolePermission(
                id=f"rp-{uuid.uuid4().hex[:12]}",
                role_id=role_id,
                permission_id=pid,
            )
        )


def _assert_user_scope(current: User, target_user_id: str) -> None:
    if current.role == "Admin" or current.username == target_user_id:
        return
    raise HTTPException(status_code=403, detail="Not allowed to view this user")


def _serialize_role(session: Session, role_id: str) -> dict[str, Any]:
    r = session.get(Role, role_id)
    if not r or not r.is_active:
        raise HTTPException(status_code=404, detail="Role not found")
    perms = session.exec(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.resource, Permission.action)
    ).all()
    return {
        "id": r.id,
        "name": r.name,
        "slug": r.slug,
        "description": r.description or "",
        "is_system": bool(r.is_system),
        "is_active": bool(r.is_active),
        "created_at": r.created_at.isoformat(),
        "permissions": [
            {
                "id": p.id,
                "resource": p.resource,
                "action": p.action,
                "description": p.description or "",
            }
            for p in perms
        ],
    }


def _user_roles_payload(session: Session, user_id: str) -> dict[str, Any]:
    grants, slugs = collect_all_grants_for_user(session, user_id)
    urs = session.exec(select(UserRole).where(UserRole.user_id == user_id)).all()
    assignments = []
    for ur in urs:
        role = session.get(Role, ur.role_id)
        if not role or not role.is_active:
            continue
        assignments.append(
            {
                "id": ur.id,
                "role_id": ur.role_id,
                "role_slug": role.slug,
                "role_name": role.name,
                "scope_type": ur.scope_type or "global",
                "scope_id": ur.scope_id or "",
                "granted_by": ur.granted_by,
                "granted_at": ur.granted_at.isoformat(),
            }
        )
    return {
        "user_id": user_id,
        "assignments": assignments,
        "effective_permissions": sorted(grants),
        "role_slugs": slugs,
    }


@router.get("/roles")
def list_roles(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(select(Role).where(Role.is_active == 1).order_by(Role.name)).all()
        out: list[dict[str, Any]] = []
        for r in rows:
            pc = len(session.exec(select(RolePermission).where(RolePermission.role_id == r.id)).all())
            uc = len(session.exec(select(UserRole).where(UserRole.role_id == r.id)).all())
            out.append(
                {
                    "id": r.id,
                    "name": r.name,
                    "slug": r.slug,
                    "description": r.description or "",
                    "is_system": bool(r.is_system),
                    "is_active": bool(r.is_active),
                    "created_at": r.created_at.isoformat(),
                    "permission_count": pc,
                    "user_count": uc,
                }
            )
        return out


@router.get("/roles/{role_id}")
def get_role(role_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        return _serialize_role(session, role_id)


@router.post("/roles")
def create_role(body: RoleCreate, _admin: User = Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    rid = f"role-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        if session.exec(select(Role).where(Role.name == name)).first():
            raise HTTPException(status_code=409, detail="Role name already exists")
        slug = _ensure_unique_role_slug(session, slugify(name))
        perm_ids = _parse_perm_strings(session, list(body.permissions or []))
        row = Role(
            id=rid,
            name=name,
            slug=slug,
            description=(body.description or "").strip() or None,
            is_system=0,
            is_active=1,
            created_at=now,
        )
        session.add(row)
        session.commit()
        _replace_role_permissions(session, rid, perm_ids)
        session.commit()
        session.refresh(row)
        return _serialize_role(session, rid)


@router.put("/roles/{role_id}")
def update_role(role_id: str, body: RoleCreate, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        r = session.get(Role, role_id)
        if not r:
            raise HTTPException(status_code=404, detail="Role not found")
        if r.is_system:
            raise HTTPException(status_code=403, detail="System roles cannot be modified")
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")
        other = session.exec(select(Role).where(Role.name == name, Role.id != role_id)).first()
        if other:
            raise HTTPException(status_code=409, detail="Role name already exists")
        r.name = name
        r.slug = _ensure_unique_role_slug(session, slugify(name), exclude_id=role_id)
        r.description = (body.description or "").strip() or None
        session.add(r)
        perm_ids = _parse_perm_strings(session, list(body.permissions or []))
        _replace_role_permissions(session, role_id, perm_ids)
        session.commit()
        session.refresh(r)
        return _serialize_role(session, role_id)


@router.delete("/roles/{role_id}")
def delete_role(role_id: str, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        r = session.get(Role, role_id)
        if not r:
            raise HTTPException(status_code=404, detail="Role not found")
        if r.is_system:
            raise HTTPException(status_code=403, detail="System roles cannot be deleted")
        for rp in session.exec(select(RolePermission).where(RolePermission.role_id == role_id)).all():
            session.delete(rp)
        for ur in session.exec(select(UserRole).where(UserRole.role_id == role_id)).all():
            session.delete(ur)
        r.is_active = 0
        session.add(r)
        session.commit()
        return {"deleted": True}


@router.get("/permissions")
def list_permissions_grouped(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(select(Permission).order_by(Permission.resource, Permission.action)).all()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for p in rows:
            grouped.setdefault(p.resource, []).append(
                {
                    "id": p.id,
                    "action": p.action,
                    "description": p.description or "",
                }
            )
        return grouped


@router.get("/users/{user_id}/roles")
def get_user_roles(user_id: str, current_user: User = Depends(get_current_user)):
    _assert_user_scope(current_user, user_id)
    with Session(engine) as session:
        return _user_roles_payload(session, user_id)


@router.post("/users/{user_id}/roles")
def assign_user_role(
    user_id: str,
    body: UserRoleAssign,
    _admin: User = Depends(require_admin),
):
    if body.user_id != user_id:
        raise HTTPException(status_code=400, detail="user_id in path and body must match")
    scope_type = (body.scope_type or "global").strip() or "global"
    scope_id = (body.scope_id or "").strip()
    with Session(engine) as session:
        role = session.get(Role, body.role_id)
        if not role or not role.is_active:
            raise HTTPException(status_code=404, detail="Role not found")
        q = select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == body.role_id,
            UserRole.scope_type == scope_type,
            UserRole.scope_id == scope_id,
        )
        if session.exec(q).first():
            return _user_roles_payload(session, user_id)
        session.add(
            UserRole(
                id=f"ur-{uuid.uuid4().hex[:10]}",
                user_id=user_id,
                role_id=body.role_id,
                scope_type=scope_type,
                scope_id=scope_id,
                granted_by=_admin.username,
                granted_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        return _user_roles_payload(session, user_id)


@router.delete("/users/{user_id}/roles/{role_id}")
def remove_user_role(user_id: str, role_id: str, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        rows = session.exec(select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)).all()
        if not rows:
            raise HTTPException(status_code=404, detail="Assignment not found")
        for ur in rows:
            session.delete(ur)
        session.commit()
        return {"removed": True}


@router.get("/users/{user_id}/permissions")
def get_user_permissions_flat(user_id: str, current_user: User = Depends(get_current_user)):
    _assert_user_scope(current_user, user_id)
    with Session(engine) as session:
        grants, slugs = collect_all_grants_for_user(session, user_id)
        return {
            "user_id": user_id,
            "permissions": sorted(grants),
            "roles": slugs,
        }


@router.post("/check")
def check_permission(body: PermissionCheckBody, current_user: User = Depends(get_current_user)):
    if current_user.role != "Admin" and body.user_id != current_user.username:
        raise HTTPException(status_code=403, detail="Can only check permissions for self")
    with Session(engine) as session:
        allowed, reason = check_user_permission(
            session,
            body.user_id,
            body.resource,
            body.action,
            body.scope_type,
            body.scope_id,
        )
        return {"allowed": allowed, "reason": reason}
