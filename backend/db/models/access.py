"""Access provisioning, change management, and compliance tables (Sprint 5)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class AccessRequestRecord(SQLModel, table=True):
    """Access grant request routed to a resource owner (Sprint 5)."""

    __tablename__ = "access_request_records"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    requester_username: str = Field(index=True)
    subject_username: str = Field(index=True)
    resource_type: str = Field(index=True)  # github_team | okta_group | k8s_role | aws_iam_role | jira_project
    resource_id: str = Field(index=True)
    resource_name: str = Field(default="")
    justification: str = Field(default="", sa_column=Column(Text))
    duration_hours: Optional[int] = Field(default=None)
    status: str = Field(default="pending_approval", index=True)
    # pending_approval | approved | rejected | provisioned | expired | revoked
    owner_username: str = Field(index=True)
    owner_missing: bool = Field(default=False)
    policy_assessment_json: str = Field(default="{}", sa_column=Column(Text))
    connector: Optional[str] = Field(default=None)
    connector_method: Optional[str] = Field(default=None)
    connector_params_json: str = Field(default="{}", sa_column=Column(Text))
    approved_by: Optional[str] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    provisioned_at: Optional[datetime] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    warning_sent_at: Optional[datetime] = Field(default=None)
    revoked_at: Optional[datetime] = Field(default=None)
    revoked_by: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResourceOwner(SQLModel, table=True):
    """Maps a resource to the person who approves access to it."""

    __tablename__ = "resource_owners"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    resource_type: str = Field(index=True)
    resource_id: str = Field(index=True)
    resource_name: str = Field(default="")
    owner_username: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChangeRecord(SQLModel, table=True):
    """Auditable production change linked to an artifact/agent run."""

    __tablename__ = "change_records"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    workspace_id: Optional[str] = Field(default=None, index=True)
    change_type: str = Field(index=True)  # deploy | terraform_apply | migration | security_remediation
    source_run_id: Optional[str] = Field(default=None, index=True)
    source_artifact_id: Optional[str] = Field(default=None, index=True)
    title: str = Field(default="")
    description: str = Field(default="", sa_column=Column(Text))
    risk: str = Field(default="moderate")  # low | moderate | high
    blast_radius_json: str = Field(default="{}", sa_column=Column(Text))
    rollback_plan: str = Field(default="", sa_column=Column(Text))
    external_id: Optional[str] = Field(default=None)
    external_url: Optional[str] = Field(default=None)
    status: str = Field(default="draft", index=True)
    # draft | submitted | approved | rejected | implemented | closed
    submitted_at: Optional[datetime] = Field(default=None)
    approved_at: Optional[datetime] = Field(default=None)
    implemented_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)
    outcome: Optional[str] = Field(default=None)  # success | failed | rolled_back
    incident_id: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ControlEvidence(SQLModel, table=True):
    """Collected audit evidence for a compliance control (SOC2 mapping)."""

    __tablename__ = "control_evidence"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    control_id: str = Field(index=True)
    control_name: str = Field(default="")
    period_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    period_end: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    evidence_json: str = Field(default="[]", sa_column=Column(Text))
    gap_count: int = Field(default=0)
    gaps_json: str = Field(default="[]", sa_column=Column(Text))
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    collected_by: str = Field(default="")


class TeamAccessTemplate(SQLModel, table=True):
    """Per-team resource template used by onboarding."""

    __tablename__ = "team_access_templates"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(default="default", index=True)
    team_name: str = Field(index=True)
    role_level: str = Field(default="junior", index=True)  # junior | senior | lead
    resources_json: str = Field(default="[]", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
