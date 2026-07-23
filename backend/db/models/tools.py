"""Tool catalog, accounts, connection logs, import history, workspace tool connections."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

class Tool(SQLModel, table=True):
    """Catalog row for an integration / platform tool type (see /api/tools)."""
    __tablename__ = "tools"

    id: str = Field(primary_key=True)
    name: str
    category: str
    description: Optional[str] = None
    icon: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolAccount(SQLModel, table=True):
    __tablename__ = "tool_accounts"

    id: str = Field(primary_key=True)
    tool_id: str = Field(foreign_key="tools.id")
    account_name: str
    account_identifier: Optional[str] = None
    instance_url: Optional[str] = None
    environment: str
    region: Optional[str] = None
    auth_type: str
    credentials_vault_ref: Optional[str] = None
    status: str = Field(default="unknown")
    is_active: int = Field(default=1)
    requires_hitl: int = Field(default=0)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # TODO(S2-P2.1): Add tenant_id/org_id fields to support multi-tenant isolation
    tenant_id: Optional[str] = Field(default="default", index=True)


class ToolConnectionLog(SQLModel, table=True):
    __tablename__ = "tool_connection_logs"

    id: str = Field(primary_key=True)
    account_id: str = Field(foreign_key="tool_accounts.id")
    status: str
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImportHistory(SQLModel, table=True):
    """Audit log for bulk import / discovery confirm operations."""

    __tablename__ = "import_history"

    id: str = Field(primary_key=True)
    import_type: str
    source: str = Field(default="")
    total_rows: int = Field(default=0)
    imported: int = Field(default=0)
    skipped: int = Field(default=0)
    failed: int = Field(default=0)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolConnection(SQLModel, table=True):
    """Workspace-scoped tool credentials (agent pipeline)."""

    __tablename__ = "tool_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "tool_id", "account_alias", name="uq_tool_conn_ws_tool_alias"),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    workspace_id: str = Field(index=True)
    tool_id: str = Field(index=True)
    account_name: str
    account_alias: str
    auth_type: str
    credentials: str = Field(default="{}")
    config: str = Field(default="{}")
    status: str = Field(default="disconnected")
    last_tested_at: Optional[datetime] = Field(default=None)
    connected_by: str = Field(default="")
    workspace_scoped: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
