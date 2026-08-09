"""Editor file persistence and PR approval records (anti-TOCTOU)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

VALID_SOURCE_TYPES = frozenset({"scratch", "github", "catalog_entity"})


class EditorFile(SQLModel, table=True):
    """Tenant + owner scoped editor buffer."""

    __tablename__ = "editor_files"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    owner_username: str = Field(index=True)
    filename: str = Field(default="untitled.yaml")
    language: str = Field(default="yaml")
    content: str = Field(default="", sa_column=Column(Text))
    source_type: str = Field(default="scratch")
    source_repo: Optional[str] = Field(default=None)
    source_path: Optional[str] = Field(default=None)
    source_ref: Optional[str] = Field(default=None)
    source_sha: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EditorPRApproval(SQLModel, table=True):
    """Immutable PR proposal — committed content is frozen at create time."""

    __tablename__ = "editor_pr_approvals"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    file_id: str = Field(index=True)
    repo: str = Field(default="")
    path: str = Field(default="")
    branch_name: str = Field(default="")
    base_branch: str = Field(default="main")
    title: str = Field(default="")
    body: str = Field(default="", sa_column=Column(Text))
    content: str = Field(default="", sa_column=Column(Text))
    base_sha: Optional[str] = Field(default=None)
    idempotency_key: str = Field(index=True)
    status: str = Field(default="pending", index=True)  # pending|approved|denied|failed
    agent_run_id: Optional[str] = Field(default=None, index=True)
    pr_url: Optional[str] = Field(default=None)
    pr_number: Optional[int] = Field(default=None)
    decided_by: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: Optional[datetime] = Field(default=None)
