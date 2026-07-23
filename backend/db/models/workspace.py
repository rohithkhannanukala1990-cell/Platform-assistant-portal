"""Workspaces, members, and templates."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

class Workspace(SQLModel, table=True):
    """Saved grouping of tools + accounts by purpose (multi-account workspaces)."""

    __tablename__ = "workspaces"

    id: str = Field(primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    description: Optional[str] = None
    icon: str = Field(default="🗂️")
    color: str = Field(default="#6366f1")
    environment: str = Field(default="production")
    tags: str = Field(default="[]")  # JSON array string
    is_active: int = Field(default=1)
    is_pinned: int = Field(default=0)
    created_by: Optional[str] = Field(default="admin")
    canvas_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # TODO(S2-P2.1): Add tenant_id/org_id fields to support multi-tenant isolation
    tenant_id: Optional[str] = Field(default="default", index=True)
    # Per-workspace flags (HITL mode, connectors, golden paths) — JSON object string.
    settings_json: str = Field(default="{}", sa_column=Column(Text))


class WorkspaceTool(SQLModel, table=True):
    """Tool (and optional account) membership in a workspace."""

    __tablename__ = "workspace_tools"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.id", index=True)
    tool_id: str = Field(foreign_key="tools.id")
    account_id: Optional[str] = Field(default=None, foreign_key="tool_accounts.id")
    display_order: int = Field(default=0)
    is_primary: int = Field(default=0)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkspaceMember(SQLModel, table=True):
    """User membership on a workspace (user_id is username / subject string)."""

    __tablename__ = "workspace_members"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspaces.id", index=True)
    user_id: str = Field(index=True)
    role: str = Field(default="viewer")
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Template(SQLModel, table=True):
    """Admin-defined reusable blueprint for workspaces."""

    __tablename__ = "templates"

    id: str = Field(primary_key=True)
    name: str
    slug: str = Field(unique=True, index=True)
    description: Optional[str] = None
    icon: str = Field(default="📋")
    color: str = Field(default="#6366f1")
    category: str = Field(default="general")
    environment: str = Field(default="production")
    tags: str = Field(default="[]")  # JSON array string
    # JSON array of golden-path slugs recommended for this blueprint.
    recommended_golden_path_keys: str = Field(default="[]")
    is_active: int = Field(default=1)
    is_published: int = Field(default=0)
    use_count: int = Field(default=0)
    created_by: Optional[str] = Field(default="admin")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TemplateTool(SQLModel, table=True):
    """Tool line item on a template."""

    __tablename__ = "template_tools"

    id: str = Field(primary_key=True)
    template_id: str = Field(foreign_key="templates.id", index=True)
    tool_id: str = Field(foreign_key="tools.id", index=True)
    account_id: Optional[str] = Field(default=None, foreign_key="tool_accounts.id")
    display_order: int = Field(default=0)
    is_required: int = Field(default=1)
    config_hints: str = Field(default="{}")  # JSON object string


class TemplateApplication(SQLModel, table=True):
    """Record of a workspace created from a template."""

    __tablename__ = "template_applications"

    id: str = Field(primary_key=True)
    template_id: str = Field(foreign_key="templates.id", index=True)
    workspace_id: str = Field(foreign_key="workspaces.id", index=True)
    applied_by: Optional[str] = Field(default="admin")
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
