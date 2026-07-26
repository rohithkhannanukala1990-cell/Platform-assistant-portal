"""MCP client tables: external server configs and bridged tool calls (Phase M1)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class MCPServer(SQLModel, table=True):
    """An external MCP server the portal connects to as a client."""

    __tablename__ = "mcp_servers"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    # stdio: spawn `command` + args_json. sse: JSON-RPC over HTTP at `url`.
    transport: str = Field(default="stdio")
    command: str = Field(default="")
    args_json: str = Field(default="[]")
    url: str = Field(default="")
    # Fernet(JSON object) — process env / headers passed to the server.
    env_encrypted: Optional[str] = Field(default=None)
    enabled: bool = Field(default=True, index=True)
    require_hitl: bool = Field(default=True)
    # Empty list means "every discovered tool is callable".
    allowlist_json: str = Field(default="[]")
    tenant_id: Optional[str] = Field(default="default", index=True)
    created_by: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCPToolCall(SQLModel, table=True):
    """Audit + HITL record for every MCP tools/call routed through the bridge."""

    __tablename__ = "mcp_tool_calls"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    server_id: str = Field(index=True)
    server_name: str = Field(default="")
    tool_name: str = Field(index=True)
    arguments_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    # pending_approval | completed | error | rejected
    status: str = Field(default="pending_approval", index=True)
    requires_hitl: bool = Field(default=True)
    dangerous: bool = Field(default=False)
    source: str = Field(default="api")
    requested_by: str = Field(default="", index=True)
    approved_by: Optional[str] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    executed_at: Optional[datetime] = Field(default=None)
    tenant_id: Optional[str] = Field(default="default", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
