"""Terminal command history and pending shell approvals."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class TerminalHistory(SQLModel, table=True):
    """Per-user shell history (last 100 commands enforced on insert)."""

    __tablename__ = "terminal_history"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    command: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class TerminalApproval(SQLModel, table=True):
    """Inline terminal HITL — command string is immutable after create (anti-TOCTOU)."""

    __tablename__ = "terminal_approvals"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    command: str = Field(default="")  # exact string to execute after grant
    reasons_json: str = Field(default="[]")
    status: str = Field(default="pending", index=True)  # pending|approved|denied|cancelled
    session_id: str = Field(default="", index=True)
    agent_run_id: Optional[str] = Field(default=None, index=True)
    decided_by: Optional[str] = Field(default=None)
    decision_reason: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: Optional[datetime] = Field(default=None)
