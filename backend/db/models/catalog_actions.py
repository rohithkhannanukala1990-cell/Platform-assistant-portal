"""Catalog self-service actions (Phase G6)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"

VALID_RISKS = {RISK_LOW, RISK_MEDIUM, RISK_HIGH}

ACTION_RUN_GOLDEN_PATH = "run_golden_path"
ACTION_REQUEST_SCORECARD_REFRESH = "request_scorecard_refresh"
ACTION_OPEN_INCIDENT = "open_incident"
ACTION_PROPOSE_DEPLOY = "propose_deploy"

BUILTIN_ACTION_TYPES = {
    ACTION_RUN_GOLDEN_PATH,
    ACTION_REQUEST_SCORECARD_REFRESH,
    ACTION_OPEN_INCIDENT,
    ACTION_PROPOSE_DEPLOY,
}


class CatalogAction(SQLModel, table=True):
    """Tenant-scoped self-service action available on catalog entities."""

    __tablename__ = "catalog_actions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str = Field(index=True)
    entity_kind: str = Field(default="all", index=True)  # all | Service | API | …
    action_type: str = Field(index=True)
    payload_template: str = Field(default="{}")  # JSON template
    risk: str = Field(default=RISK_LOW)
    require_hitl: bool = Field(default=False)
    tenant_id: Optional[str] = Field(default="default", index=True)
    enabled: bool = Field(default=True)
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
