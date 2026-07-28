"""Alert correlation rules and grouping state (Phase G4)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

ACTION_CREATE_INCIDENT = "create_incident"
ACTION_SUPPRESS = "suppress"
ACTION_ATTACH_EXISTING = "attach_existing"

VALID_ALERT_ACTIONS = {
    ACTION_CREATE_INCIDENT,
    ACTION_SUPPRESS,
    ACTION_ATTACH_EXISTING,
}


class AlertRule(SQLModel, table=True):
    """Tenant-scoped rules-based alert correlation (not ML)."""

    __tablename__ = "alert_rules"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    name: str = Field(index=True)
    match_service: Optional[str] = Field(default=None)
    match_severity: Optional[str] = Field(default=None)
    match_title_regex: Optional[str] = Field(default=None)
    group_window_sec: int = Field(default=300)
    action: str = Field(default=ACTION_CREATE_INCIDENT)
    priority: int = Field(default=100, index=True)
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertGroupBucket(SQLModel, table=True):
    """Tracks grouped alerts within a rule's time window."""

    __tablename__ = "alert_group_buckets"

    id: str = Field(primary_key=True)  # fingerprint key
    tenant_id: str = Field(index=True)
    rule_id: str = Field(index=True)
    incident_id: int = Field(index=True)
    fingerprint: str = Field(index=True)
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alert_count: int = Field(default=1)
