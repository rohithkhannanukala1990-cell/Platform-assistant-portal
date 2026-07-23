"""RBAC roles, permissions, and assignments."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

class Role(SQLModel, table=True):
    """RBAC role definition (system or custom)."""

    __tablename__ = "roles"

    id: str = Field(primary_key=True)
    name: str = Field(unique=True)
    slug: str = Field(unique=True, index=True)
    description: Optional[str] = None
    is_system: int = Field(default=0)
    is_active: int = Field(default=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Permission(SQLModel, table=True):
    """Atomic permission (resource + action)."""

    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("resource", "action", name="uq_permissions_resource_action"),)

    id: str = Field(primary_key=True)
    resource: str = Field(index=True)
    action: str = Field(index=True)
    description: Optional[str] = None


class RolePermission(SQLModel, table=True):
    """Many-to-many role ↔ permission."""

    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_role_permissions_role_perm"),)

    id: str = Field(primary_key=True)
    role_id: str = Field(foreign_key="roles.id", index=True)
    permission_id: str = Field(foreign_key="permissions.id", index=True)


class UserRole(SQLModel, table=True):
    """Assignment of a role to a user (global or scoped)."""

    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_type", "scope_id", name="uq_user_roles_scope"),
    )

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    role_id: str = Field(foreign_key="roles.id", index=True)
    scope_type: str = Field(default="global")
    scope_id: str = Field(default="")
    granted_by: Optional[str] = Field(default="admin")
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
