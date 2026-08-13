"""User context, access requests, and account grants."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

class UserContext(SQLModel, table=True):
    """Per-user active tool account selections (Sprint 1+ multi-account context)."""

    __tablename__ = "user_context"

    user_id: str = Field(primary_key=True)
    active_environment: str = Field(default="development")
    active_accounts: str = Field(default="{}")  # JSON: { tool_id: account_id }
    pinned_accounts: str = Field(default="[]")  # JSON: [account_id, ...]
    last_switched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    workspace_id: Optional[str] = Field(default=None, index=True)
    tenant_id: Optional[str] = Field(default="default", index=True)


class AccessRequest(SQLModel, table=True):
    """Request access to a tool account (admin review workflow)."""

    __tablename__ = "access_requests"

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    account_id: str = Field(foreign_key="tool_accounts.id", index=True)
    reason: str
    status: str = Field(default="pending")
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserAccountAccess(SQLModel, table=True):
    """Granted account access after an access request is approved."""

    __tablename__ = "user_account_access"
    __table_args__ = (UniqueConstraint("user_id", "account_id", name="uq_user_account_access"),)

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    account_id: str = Field(foreign_key="tool_accounts.id", index=True)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
