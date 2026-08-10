"""Slack account linking (Sprint 6) — maps a Slack user to a portal user so
interactive-message approvals can be attributed and RBAC-checked."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class SlackUserLink(SQLModel, table=True):
    """Confirmed link between a Slack user and a portal account."""

    __tablename__ = "slack_user_links"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    slack_user_id: str = Field(index=True)
    slack_team_id: Optional[str] = Field(default=None, index=True)
    portal_username: str = Field(index=True)
    linked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlackLinkCode(SQLModel, table=True):
    """Short-lived one-time code a user generates in the portal and redeems in
    Slack (via ``/portal-link <code>``) to complete account linking."""

    __tablename__ = "slack_link_codes"

    code: str = Field(primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    portal_username: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(index=True)
    used_at: Optional[datetime] = Field(default=None)
