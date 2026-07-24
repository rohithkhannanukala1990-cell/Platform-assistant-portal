"""Ops / platform tables: incidents, infra, CI/CD, notifications, settings, webhooks, health."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

class Incident(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str
    summary: str
    root_cause: str
    evidence_json: str = Field(default="[]")
    action_plan_json: str = Field(default="[]")
    commands_json: str = Field(default="[]")
    files_to_check_json: str = Field(default="[]")
    validation_steps_json: str = Field(default="[]")
    raw_logs: str
    model_used: str
    raw_response: str
    source: str = Field(default="manual")        # "manual" | "webhook:<source-name>"
    status: str = Field(default="OPEN")
    # OPEN | RESOLVED | AWAITING_APPROVAL | RESOLVED_BY_AGENT | REJECTED
    execution_logs: Optional[str] = Field(default=None)
    owner_role: str = Field(default="Admin")     # Admin | Developer | DataEngineer | NetworkEngineer
    proposed_remediation_plan: Optional[str] = Field(default=None)  # JSON array of steps
    agent_execution_logs: Optional[str] = Field(default=None)
    tenant_id: Optional[str] = Field(default="default", index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)


class InfraGeneration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prompt: str
    resource_name: str
    provider_used: str
    terraform_code: str
    cli_commands_json: str = Field(default="[]")
    cost_estimate: str
    model_used: str


class CICDPipeline(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    prompt: str
    tool_name: str
    yaml_code: str
    explanation: str
    security_checks_json: str = Field(default="[]")
    model_used: str


class Notification(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    type: str = Field(default="info")   # info | warning | critical | error
    is_read: bool = Field(default=False)
    incident_id: Optional[int] = Field(default=None)


class UserSetting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = Field(default="")


class WebhookEvent(SQLModel, table=True):
    id: Optional[int]   = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str                              # github | airflow | snowflake | aws | datadog | …
    event_type: str    = Field(default="")  # push | alert | dag_failure | …
    owner_role: str    = Field(default="Admin")
    status: str        = Field(default="accepted")   # accepted | processed | error
    incident_id: Optional[int] = Field(default=None)
    raw_payload: str   = Field(default="{}")         # JSON-encoded original body
    cloud_event_id: str = Field(default="")          # generated CE id


class HealthAlert(SQLModel, table=True):
    """Background health-check / auto-heal notifications (see health_alerts.py)."""
    id: str = Field(primary_key=True)
    user_id: str = Field(default="")
    message: str = Field(default="")
    severity: str = Field(default="info")   # info | warning | critical
    status: str = Field(default="active")   # active | resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
