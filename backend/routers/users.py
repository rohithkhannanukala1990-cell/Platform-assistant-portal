"""Admin user management API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlmodel import Session, select

from ..services.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamp_page

from ..auth import (
    VALID_ROLES,
    User,
    get_current_user,
    hash_password,
    normalize_role,
    require_admin,
    sync_user_rbac_role,
    write_audit,
)
from ..context import DEFAULT_TENANT_ID, resolve_tenant_id
from ..database import UserAgentPermission, engine, get_db

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_PERMISSIONS = {"observe", "execute", "automate"}


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None


class UserCreateBody(BaseModel):
    username: str
    email: str = ""
    password: str
    role: str = "User"
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None


class UserPatchBody(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None
    tenant_id: Optional[str] = None
    workspace_id: Optional[str] = None


class PermissionBody(BaseModel):
    agent_name: str
    permission_level: str


class PermissionOut(BaseModel):
    id: str
    user_id: int
    agent_name: str
    permission_level: str
    created_at: datetime


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email or "",
        role=normalize_role(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
        last_login=user.last_login,
        tenant_id=getattr(user, "tenant_id", None) or DEFAULT_TENANT_ID,
        workspace_id=getattr(user, "workspace_id", None),
    )


def _admin_tenant(admin: User) -> str:
    return resolve_tenant_id(getattr(admin, "tenant_id", None), DEFAULT_TENANT_ID)


def _audit_action(
    admin: User,
    action: str,
    resource: str,
    request: Request | None = None,
    **extra,
) -> None:
    detail = json.dumps({"action": action, "status": "success", **extra})
    write_audit(
        actor=admin.username,
        actor_role=normalize_role(admin.role),
        event_type=action,
        resource=resource,
        detail=detail,
        ip_address=(request.client.host if request and request.client else ""),
    )


@router.get("/", response_model=list[UserOut])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    _admin: User = Depends(require_admin),
):
    tenant = _admin_tenant(_admin)
    _, size, offset = clamp_page(page, page_size)
    with Session(engine) as session:
        q = select(User).order_by(User.username)
        # Scope to the admin's tenant; legacy NULL/empty tenant rows count as default.
        if tenant == DEFAULT_TENANT_ID:
            q = q.where(
                or_(
                    User.tenant_id == tenant,
                    User.tenant_id.is_(None),  # type: ignore[union-attr]
                    User.tenant_id == "",
                )
            )
        else:
            q = q.where(User.tenant_id == tenant)
        rows = session.exec(q.offset(offset).limit(size)).all()
    return [_user_out(u) for u in rows]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateBody,
    request: Request,
    admin: User = Depends(require_admin),
):
    role = normalize_role(body.role)
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    tenant_id = (body.tenant_id or "").strip() or None
    workspace_id = (body.workspace_id or "").strip() or None
    if not tenant_id and not workspace_id:
        # Inherit admin tenant for demo/single-tenant; still enforce association.
        tenant_id = _admin_tenant(admin)
    if not tenant_id and not workspace_id:
        raise HTTPException(
            status_code=400,
            detail="tenant_id or workspace_id is required",
        )
    tenant_id = resolve_tenant_id(tenant_id, _admin_tenant(admin))
    # Admins may only create users in their own tenant.
    if tenant_id != _admin_tenant(admin):
        raise HTTPException(
            status_code=403,
            detail="Cannot create users for another tenant",
        )

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == body.username)).first()
        if existing:
            raise HTTPException(status_code=409, detail="Username already exists")
        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            role=role,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        session.add(user)
        session.flush()
        sync_user_rbac_role(session, user, granted_by=admin.username)
        session.commit()
        session.refresh(user)

    _audit_action(
        admin,
        "user_created",
        f"user:{user.username}",
        request,
        user_id=user.username,
        role=role,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
    return _user_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatchBody,
    request: Request,
    admin: User = Depends(require_admin),
):
    admin_tenant = _admin_tenant(admin)
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_tenant = resolve_tenant_id(getattr(user, "tenant_id", None), DEFAULT_TENANT_ID)
        if user_tenant != admin_tenant:
            raise HTTPException(status_code=404, detail="User not found")

        if body.role is not None:
            user.role = normalize_role(body.role)
            sync_user_rbac_role(session, user, granted_by=admin.username)
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.email is not None:
            user.email = body.email
        if body.tenant_id is not None:
            new_tenant = resolve_tenant_id(body.tenant_id)
            if new_tenant != admin_tenant:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot move users to another tenant",
                )
            user.tenant_id = new_tenant
        if body.workspace_id is not None:
            user.workspace_id = (body.workspace_id or "").strip() or None
            if not getattr(user, "tenant_id", None) and not user.workspace_id:
                raise HTTPException(
                    status_code=400,
                    detail="tenant_id or workspace_id is required",
                )
        session.add(user)
        session.commit()
        session.refresh(user)

    _audit_action(
        admin,
        "user_updated",
        f"user:{user.username}",
        request,
        user_id=user.username,
    )
    return _user_out(user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
):
    if admin.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    admin_tenant = _admin_tenant(admin)
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user_tenant = resolve_tenant_id(getattr(user, "tenant_id", None), DEFAULT_TENANT_ID)
        if user_tenant != admin_tenant:
            raise HTTPException(status_code=404, detail="User not found")
        username = user.username
        perms = session.exec(
            select(UserAgentPermission).where(UserAgentPermission.user_id == user_id)
        ).all()
        for p in perms:
            session.delete(p)
        session.delete(user)
        session.commit()

    _audit_action(admin, "user_deleted", f"user:{username}", request, user_id=username)
    return {"deleted": True}


@router.get("/{user_id}/permissions", response_model=list[PermissionOut])
def list_permissions(user_id: int, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        if not session.get(User, user_id):
            raise HTTPException(status_code=404, detail="User not found")
        rows = session.exec(
            select(UserAgentPermission).where(UserAgentPermission.user_id == user_id)
        ).all()
    return [
        PermissionOut(
            id=r.id,
            user_id=r.user_id,
            agent_name=r.agent_name,
            permission_level=r.permission_level,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/{user_id}/permissions", response_model=PermissionOut, status_code=status.HTTP_201_CREATED)
def grant_permission(
    user_id: int,
    body: PermissionBody,
    request: Request,
    admin: User = Depends(require_admin),
):
    level = body.permission_level.lower()
    if level not in VALID_PERMISSIONS:
        raise HTTPException(status_code=400, detail="Invalid permission level")

    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        existing = session.exec(
            select(UserAgentPermission).where(
                UserAgentPermission.user_id == user_id,
                UserAgentPermission.agent_name == body.agent_name,
            )
        ).first()
        if existing:
            existing.permission_level = level
            session.add(existing)
            session.commit()
            session.refresh(existing)
            row = existing
        else:
            row = UserAgentPermission(
                user_id=user_id,
                agent_name=body.agent_name,
                permission_level=level,
                created_at=datetime.now(timezone.utc),
            )
            session.add(row)
            session.commit()
            session.refresh(row)

    _audit_action(
        admin,
        "permission_granted",
        f"user:{user.username}/agent:{body.agent_name}",
        request,
        user_id=user.username,
        agent_name=body.agent_name,
        permission_level=level,
    )
    return PermissionOut(
        id=row.id,
        user_id=row.user_id,
        agent_name=row.agent_name,
        permission_level=row.permission_level,
        created_at=row.created_at,
    )


@router.delete("/{user_id}/permissions/{permission_id}")
def revoke_permission(
    user_id: int,
    permission_id: str,
    request: Request,
    admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        row = session.get(UserAgentPermission, permission_id)
        if not row or row.user_id != user_id:
            raise HTTPException(status_code=404, detail="Permission not found")
        agent_name = row.agent_name
        session.delete(row)
        session.commit()

    _audit_action(
        admin,
        "permission_revoked",
        f"user:{user.username}/agent:{agent_name}",
        request,
        user_id=user.username,
        agent_name=agent_name,
    )
    return {"revoked": True}


class RoleUpdateRequest(BaseModel):
    role: str


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: int,
    body: RoleUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if normalize_role(current_user.role) != "Admin":
        raise HTTPException(status_code=403, detail="Only Admins can change roles")

    role = normalize_role(body.role)
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role must be one of {sorted(VALID_ROLES)}",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role
    sync_user_rbac_role(db, user, granted_by=current_user.username)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "role": user.role}
