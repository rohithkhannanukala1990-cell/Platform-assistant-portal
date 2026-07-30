"""Ops / platform tables: incidents, infra, CI/CD, notifications, settings, webhooks, health."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

class Incident(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )
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
    status: str = Field(default="OPEN", index=True)
    # OPEN | RESOLVED | AWAITING_APPROVAL | RESOLVED_BY_AGENT | REJECTED
    execution_logs: Optional[str] = Field(default=None)
    owner_role: str = Field(default="Admin")     # Admin | Developer | DataEngineer | NetworkEngineer
    proposed_remediation_plan: Optional[str] = Field(default=None)  # JSON array of steps
    agent_execution_logs: Optional[str] = Field(default=None)
    tenant_id: Optional[str] = Field(default="default", index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    timeline_json: Optional[str] = Field(default="[]")  # JSON array of timeline events


class IncidentPostmortem(SQLModel, table=True):
    """Versioned postmortem document for an incident (Phase G3/P5)."""

    __tablename__ = "incident_postmortems"

    id: Optional[int] = Field(default=None, primary_key=True)
    incident_id: int = Field(index=True)
    tenant_id: str = Field(default="default", index=True)
    version: int = Field(default=1, index=True)
    markdown: str = Field(default="")
    sections_json: str = Field(default="{}")
    action_items_json: str = Field(default="[]")  # checklist / catalog action links
    template_variant: str = Field(default="SEV2")  # SEV1 | SEV2
    generated_by: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    source: str                              # github | airflow | snowflake | aws | datadog | …
    event_type: str    = Field(default="")  # push | alert | dag_failure | …
    owner_role: str    = Field(default="Admin")
    status: str        = Field(default="accepted")   # accepted | processed | error
    incident_id: Optional[int] = Field(default=None)
    raw_payload: str   = Field(default="{}")         # JSON-encoded original body
    cloud_event_id: str = Field(default="", index=True)  # delivery / CE id for idempotency lookup


class WebhookDelivery(SQLModel, table=True):
    """Idempotency ledger for inbound webhooks (delivery_id primary key)."""

    __tablename__ = "webhook_delivery"

    delivery_id: str = Field(primary_key=True, max_length=255)
    source: str = Field(default="", index=True)
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = Field(default="received")  # received | processed | duplicate | error


class CeleryTaskFailure(SQLModel, table=True):
    """Dead-letter style failure log for manual replay after max Celery retries."""

    __tablename__ = "celery_task_failure"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_name: str = Field(default="", index=True)
    task_id: str = Field(default="", index=True)
    queue: str = Field(default="celery")
    args_json: str = Field(default="[]")
    kwargs_json: str = Field(default="{}")
    error: str = Field(default="")
    retries: int = Field(default=0)
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    replayed_at: Optional[datetime] = Field(default=None)


class HealthAlert(SQLModel, table=True):
    """Background health-check / auto-heal notifications (see health_alerts.py)."""
    id: str = Field(primary_key=True)
    user_id: str = Field(default="")
    message: str = Field(default="")
    severity: str = Field(default="info")   # info | warning | critical
    status: str = Field(default="active")   # active | resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
