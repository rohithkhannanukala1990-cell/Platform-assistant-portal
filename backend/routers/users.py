"""Admin user management API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import User, hash_password, normalize_role, require_admin, write_audit
from ..database import UserAgentPermission, engine

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


class UserCreateBody(BaseModel):
    username: str
    email: str = ""
    password: str
    role: str = "User"


class UserPatchBody(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None


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
    )


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
def list_users(_admin: User = Depends(require_admin)):
    with Session(engine) as session:
        rows = session.exec(select(User).order_by(User.username)).all()
    return [_user_out(u) for u in rows]


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreateBody,
    request: Request,
    admin: User = Depends(require_admin),
):
    role = normalize_role(body.role)
    if role not in {"Admin", "User"}:
        raise HTTPException(status_code=400, detail="Invalid role")

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
        )
        session.add(user)
        session.commit()
        session.refresh(user)

    _audit_action(
        admin,
        "user_created",
        f"user:{user.username}",
        request,
        user_id=user.username,
        role=role,
    )
    return _user_out(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserPatchBody,
    request: Request,
    admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if body.role is not None:
            user.role = normalize_role(body.role)
        if body.is_active is not None:
            user.is_active = body.is_active
        if body.email is not None:
            user.email = body.email
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

    with Session(engine) as session:
        user = session.get(User, user_id)
        if not user:
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
