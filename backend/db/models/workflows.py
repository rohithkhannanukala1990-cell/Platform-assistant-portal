"""Workflow definitions and runs (agent chaining with HITL gates)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

VALID_TRIGGER_TYPES = frozenset({"manual", "schedule", "event"})
VALID_RISKS = frozenset({"low", "medium", "high"})
VALID_CONCURRENT_LIMITS = frozenset({"drop", "queue"})
VALID_RUN_STATUSES = frozenset(
    {
        "pending",
        "running",
        "pending_approval",
        "completed",
        "failed",
        "rejected",
        "cancelled",
    }
)
VALID_STEP_TYPES = frozenset({"agent", "connector", "hitl", "condition"})
VALID_GROUNDING = frozenset({"live", "partial", "none", "demo"})

# Connector methods that mutate external systems — require a preceding HITL gate.
CONNECTOR_WRITE_METHODS = frozenset(
    {
        "post_message",
        "post_thread_reply",
        "notify",
        "notify_channel",
        "send_message",
        "create_incident",
        "create_issue",
        "create_pr",
        "merge_pr",
        "close_pr",
        "acknowledge",
        "resolve",
        "deploy",
        "sync",
        "scale",
        "delete",
        "apply",
        "patch",
        "update",
        "write",
        "put",
        "post",
        "create",
        "trigger_pipeline",
        "rollback",
        "restart",
        "cordon",
        "drain",
    }
)


def is_connector_write_method(method: str) -> bool:
    m = (method or "").strip().lower()
    if not m:
        return False
    if m in CONNECTOR_WRITE_METHODS:
        return True
    prefixes = (
        "post_",
        "create_",
        "delete_",
        "update_",
        "patch_",
        "send_",
        "notify_",
        "deploy_",
        "scale_",
        "apply_",
        "write_",
        "merge_",
        "trigger_",
    )
    return any(m.startswith(p) for p in prefixes)


class WorkflowDefinition(SQLModel, table=True):
    """Tenant-scoped reusable workflow DAG."""

    __tablename__ = "workflow_definitions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    steps_json: str = Field(default="[]")
    trigger_type: str = Field(default="manual")
    trigger_config_json: str = Field(default="{}")
    enabled: bool = Field(default=True)
    risk: str = Field(default="medium")
    max_runs_per_hour: int = Field(default=12)
    max_concurrent_runs: int = Field(default=1)
    on_concurrent_limit: str = Field(default="drop")  # drop | queue
    first_live_run_approved_at: Optional[datetime] = Field(default=None)
    created_by: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkflowRun(SQLModel, table=True):
    """One execution of a workflow definition."""

    __tablename__ = "workflow_runs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    workflow_id: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    current_step_id: Optional[str] = Field(default=None)
    context_json: str = Field(default="{}")
    steps_state_json: str = Field(default="{}")
    triggered_by: str = Field(default="")
    grounding: str = Field(default="none")
    dry_run: bool = Field(default=False)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None)
