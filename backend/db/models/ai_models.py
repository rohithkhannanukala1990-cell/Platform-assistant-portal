"""AI assistant conversations and agent permission/run tables."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

class AIConversation(SQLModel, table=True):
    """AI assistant chat thread (Sprint 6)."""

    __tablename__ = "ai_conversations"

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    environment: str = Field(default="production")
    title: Optional[str] = Field(default=None)
    model: str = Field(default="gemini")
    is_active: int = Field(default=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIMessage(SQLModel, table=True):
    """Single turn in an AI conversation."""

    __tablename__ = "ai_messages"

    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="ai_conversations.id", index=True)
    role: str
    content: str
    tool_calls: str = Field(default="[]")
    # Column name "metadata" (spec); Python attr cannot be "metadata" (SQLAlchemy reserved).
    message_metadata: str = Field(default="{}", sa_column=Column("metadata", Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIToolExecution(SQLModel, table=True):
    """Tracked tool / action execution from assistant flow (incl. HITL)."""

    __tablename__ = "ai_tool_executions"

    id: str = Field(primary_key=True)
    conversation_id: str = Field(foreign_key="ai_conversations.id", index=True)
    message_id: Optional[str] = Field(default=None, index=True)
    tool_id: str
    action: str
    parameters: str = Field(default="{}")
    result: str = Field(default="{}")
    status: str = Field(default="pending")
    requires_hitl: int = Field(default=0)
    approved_by: Optional[str] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    executed_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserAgentPermission(SQLModel, table=True):
    """Per-user agent access levels (observe | execute | automate)."""

    __tablename__ = "user_agent_permissions"
    __table_args__ = (UniqueConstraint("user_id", "agent_name", name="uq_user_agent"),)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: int = Field(index=True)
    agent_name: str = Field(index=True)
    permission_level: str = Field(default="observe")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentRun(SQLModel, table=True):
    """Persisted agent pipeline runs (HITL approvals)."""

    __tablename__ = "agent_runs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    agent: str = Field(default="orchestrator", index=True)
    status: str = Field(default="pending_approval", index=True)
    summary: str = Field(default="")
    details_json: str = Field(default="{}")
    requires_approval: bool = Field(default=False)
    approval_payload_json: str = Field(default="{}")
    execution_log: Optional[str] = Field(default=None)
    triggered_by: str = Field(default="", index=True)
    workspace_id: str = Field(default="", index=True)
    environment: str = Field(default="development")
    task: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
