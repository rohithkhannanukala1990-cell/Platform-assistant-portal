import json
import os
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import text as sa_text, UniqueConstraint

# Use DATABASE_URL from env.
# - Docker / production: set to postgresql://...
# - Local dev without Docker: defaults to SQLite so the server starts immediately
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./incidents.db")

# Normalise PostgreSQL scheme so psycopg2 driver is used
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

_is_postgres = DATABASE_URL.startswith("postgresql")
_is_sqlite   = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"echo": False, "pool_pre_ping": True}
if _is_postgres:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "connect_args": {"connect_timeout": 10},
    })
elif _is_sqlite:
    # SQLite doesn't support multi-threaded connection pools the same way
    _engine_kwargs.update({
        "connect_args": {"check_same_thread": False},
    })

engine = create_engine(DATABASE_URL, **_engine_kwargs)


# ── Tables ────────────────────────────────────────────────────────────────────

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


class ToolConnectionLog(SQLModel, table=True):
    __tablename__ = "tool_connection_logs"

    id: str = Field(primary_key=True)
    account_id: str = Field(foreign_key="tool_accounts.id")
    status: str
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    tested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserContext(SQLModel, table=True):
    """Per-user active tool account selections (Sprint 1+ multi-account context)."""

    __tablename__ = "user_context"

    user_id: str = Field(primary_key=True)
    active_environment: str = Field(default="development")
    active_accounts: str = Field(default="{}")  # JSON: { tool_id: account_id }
    pinned_accounts: str = Field(default="[]")  # JSON: [account_id, ...]
    last_switched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AccessRequest(SQLModel, table=True):
    """Request access to a tool account (admin review workflow)."""

    __tablename__ = "access_requests"

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    account_id: str = Field(foreign_key="tool_accounts.id", index=True)
    reason: str
    status: str = Field(default="pending")
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserAccountAccess(SQLModel, table=True):
    """Granted account access after an access request is approved."""

    __tablename__ = "user_account_access"
    __table_args__ = (UniqueConstraint("user_id", "account_id", name="uq_user_account_access"),)

    id: str = Field(primary_key=True)
    user_id: str = Field(index=True)
    account_id: str = Field(foreign_key="tool_accounts.id", index=True)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Bootstrap ─────────────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "slack_webhook_url":    "",
    "auto_triage_enabled":  "false",
    "theme":                "dark",
    "default_cloud":        "GCP",
    "default_cicd_tool":    "GitHub Actions",
    "jira_domain":          "",
    "jira_email":           "",
    "jira_api_token":       "",
    "jira_project_key":     "",
}


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    _migrate()
    _seed_settings()
    _seed_tools()


def _seed_tools() -> None:
    """Idempotent seed of built-in tool catalog rows."""
    rows: list[tuple[str, str, str, str, str]] = [
        ("aws", "AWS", "cloud", "Amazon Web Services", "☁️"),
        ("gcp", "GCP", "cloud", "Google Cloud Platform", "☁️"),
        ("azure", "Azure", "cloud", "Microsoft Azure", "☁️"),
        ("oci", "OCI", "cloud", "Oracle Cloud Infrastructure", "☁️"),
        ("github", "GitHub", "source_control", "GitHub Repositories", "🐙"),
        ("gitlab", "GitLab", "source_control", "GitLab Repositories", "🦊"),
        ("bitbucket", "Bitbucket", "source_control", "Bitbucket Repositories", "🪣"),
        ("jira", "Jira", "project_mgmt", "Jira Project Management", "📋"),
        ("linear", "Linear", "project_mgmt", "Linear Issue Tracking", "📐"),
        ("servicenow", "ServiceNow", "project_mgmt", "ServiceNow ITSM", "🔧"),
        ("slack", "Slack", "comms", "Slack Messaging", "💬"),
        ("teams", "Teams", "comms", "Microsoft Teams", "💬"),
        ("pagerduty", "PagerDuty", "comms", "PagerDuty Alerting", "🚨"),
        ("prometheus", "Prometheus", "monitoring", "Prometheus Metrics", "📊"),
        ("datadog", "Datadog", "monitoring", "Datadog Monitoring", "🐶"),
        ("grafana", "Grafana", "monitoring", "Grafana Dashboards", "📈"),
        ("newrelic", "New Relic", "monitoring", "New Relic Observability", "🔵"),
        ("postgres", "PostgreSQL", "databases", "PostgreSQL Database", "🐘"),
        ("mysql", "MySQL", "databases", "MySQL Database", "🐬"),
        ("mongodb", "MongoDB", "databases", "MongoDB NoSQL", "🍃"),
        ("redis", "Redis", "databases", "Redis Cache", "⚡"),
        ("kubernetes", "Kubernetes", "kubernetes", "Kubernetes Clusters", "🐳"),
        ("vault", "HashiCorp Vault", "secrets", "HashiCorp Vault", "🔐"),
        ("aws_sm", "AWS Secrets Manager", "secrets", "AWS Secrets Manager", "🔑"),
        ("jenkins", "Jenkins", "cicd", "Jenkins CI/CD", "⚙️"),
        ("argocd", "ArgoCD", "cicd", "ArgoCD GitOps", "🐙"),
    ]
    with Session(engine) as session:
        for tid, name, cat, desc, icon in rows:
            if session.get(Tool, tid):
                continue
            session.add(
                Tool(id=tid, name=name, category=cat, description=desc, icon=icon)
            )
        session.commit()


def _column_exists(session: Session, table: str, column: str) -> bool:
    """Works for both PostgreSQL (information_schema) and SQLite (PRAGMA)."""
    if _is_postgres:
        row = session.exec(sa_text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ).bindparams(t=table, c=column)).first()
        return row is not None
    else:
        rows = session.exec(sa_text(f"PRAGMA table_info({table})")).all()
        return any(r[1] == column for r in rows)


def _migrate():
    """
    Idempotently add columns introduced after the initial schema.
    Uses information_schema on PostgreSQL, PRAGMA on SQLite.
    """
    migrations = [
        # (table,         column,                       pg_type,   default_expr)
        ("incident",     "source",                      "TEXT",    "'manual'"),
        ("incident",     "status",                      "TEXT",    "'OPEN'"),
        ("incident",     "execution_logs",              "TEXT",    "NULL"),
        ("incident",     "owner_role",                  "TEXT",    "'Admin'"),
        ("incident",     "proposed_remediation_plan",   "TEXT",    "NULL"),
        ("incident",     "agent_execution_logs",        "TEXT",    "NULL"),
        ("notification", "incident_id",                 "INTEGER", "NULL"),
    ]
    with Session(engine) as session:
        for table, col, col_type, default in migrations:
            try:
                if not _column_exists(session, table, col):
                    default_clause = f"DEFAULT {default}" if default != "NULL" else ""
                    session.exec(sa_text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{col}" {col_type} {default_clause}'
                    ))
                    session.commit()
                    print(f"[migrate] added {table}.{col}")
            except Exception as exc:
                session.rollback()
                print(f"[migrate] {table}.{col}: {exc}")


def _seed_settings():
    """Insert default settings only if they don't already exist."""
    with Session(engine) as session:
        for key, value in DEFAULT_SETTINGS.items():
            exists = session.exec(select(UserSetting).where(UserSetting.key == key)).first()
            if not exists:
                session.add(UserSetting(key=key, value=value))
        session.commit()


# ── Incidents ─────────────────────────────────────────────────────────────────

def save_incident(data: dict) -> Incident:
    incident = Incident(
        severity=data["severity"],
        summary=data["summary"],
        root_cause=data["root_cause"],
        evidence_json=json.dumps(data.get("evidence", [])),
        action_plan_json=json.dumps(data.get("action_plan", [])),
        commands_json=json.dumps(data.get("commands", [])),
        files_to_check_json=json.dumps(data.get("files_to_check", [])),
        validation_steps_json=json.dumps(data.get("validation_steps", [])),
        raw_logs=data.get("raw_logs", ""),
        model_used=data.get("model_used", "system"),
        raw_response=data.get("raw_response", ""),
        source=data.get("source", "manual"),
        owner_role=data.get("owner_role", "Admin"),
    )
    with Session(engine) as session:
        session.add(incident)
        session.commit()
        session.refresh(incident)
    return incident


def get_all_incidents() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Incident).order_by(Incident.timestamp.desc())).all()
    return [serialize_incident(r) for r in rows]


def _serialize_incident(i: Incident) -> dict:
    return serialize_incident(i)


def _safe_json_loads(value, fallback=None):
    """Parse JSON string safely; return fallback on any error."""
    if fallback is None:
        fallback = []
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def serialize_incident(i: Incident) -> dict:
    return {
        "id": i.id,
        "timestamp": i.timestamp.isoformat(),
        "severity": i.severity,
        "summary": i.summary,
        "root_cause": i.root_cause,
        "evidence": _safe_json_loads(i.evidence_json),
        "action_plan": _safe_json_loads(i.action_plan_json),
        "commands": _safe_json_loads(i.commands_json),
        "files_to_check": _safe_json_loads(i.files_to_check_json),
        "validation_steps": _safe_json_loads(i.validation_steps_json),
        "raw_logs": i.raw_logs,
        "model_used": i.model_used,
        "raw_response": i.raw_response,
        "source":                    getattr(i, "source",                    "manual") or "manual",
        "status":                    getattr(i, "status",                    "OPEN")   or "OPEN",
        "execution_logs":            getattr(i, "execution_logs",            None),
        "owner_role":                getattr(i, "owner_role",                "Admin")  or "Admin",
        "proposed_remediation_plan": _safe_json_loads(getattr(i, "proposed_remediation_plan", None)),
        "agent_execution_logs":      getattr(i, "agent_execution_logs",      None),
    }


def update_incident_status(
    incident_id: int,
    status: str,
    execution_logs: str | None = None,
    proposed_remediation_plan: str | None = None,
    agent_execution_logs: str | None = None,
) -> dict:
    with Session(engine) as session:
        row = session.get(Incident, incident_id)
        if not row:
            raise ValueError(f"Incident {incident_id} not found")
        row.status = status
        if execution_logs is not None:
            row.execution_logs = execution_logs
        if proposed_remediation_plan is not None:
            row.proposed_remediation_plan = proposed_remediation_plan
        if agent_execution_logs is not None:
            row.agent_execution_logs = agent_execution_logs
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialize_incident(row)


_APPROVAL_STATUSES = ("AWAITING_APPROVAL", "ESCALATED_SECURITY_RISK")


def get_pending_approvals(role: str | None = None) -> list[dict]:
    """
    Return incidents that require human attention:
      - AWAITING_APPROVAL       → needs approve/reject
      - ESCALATED_SECURITY_RISK → needs manual intervention (guardrail fired)
    Optionally filtered by owner_role.
    """
    with Session(engine) as session:
        rows = session.exec(
            select(Incident)
            .where(Incident.status.in_(_APPROVAL_STATUSES))
            .order_by(Incident.timestamp.desc())
        ).all()
    results = [_serialize_incident(r) for r in rows]
    if role and role != "Admin":
        results = [r for r in results if r["owner_role"] == role]
    return results


# ── Infra Generations ─────────────────────────────────────────────────────────

def save_infra(data: dict) -> InfraGeneration:
    record = InfraGeneration(
        prompt=data["prompt"],
        resource_name=data["resource_name"],
        provider_used=data["provider_used"],
        terraform_code=data["terraform_code"],
        cli_commands_json=json.dumps(data.get("cli_commands", [])),
        cost_estimate=data["cost_estimate"],
        model_used=data["model_used"],
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def get_all_infra() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(InfraGeneration).order_by(InfraGeneration.timestamp.desc())).all()
    return [_serialize_infra(r) for r in rows]


def _serialize_infra(r: InfraGeneration) -> dict:
    return {
        "id": r.id,
        "timestamp": r.timestamp.isoformat(),
        "prompt": r.prompt,
        "resource_name": r.resource_name,
        "provider_used": r.provider_used,
        "terraform_code": r.terraform_code,
        "cli_commands": _safe_json_loads(r.cli_commands_json),
        "cost_estimate": r.cost_estimate,
        "model_used": r.model_used,
    }


# ── CI/CD Pipelines ───────────────────────────────────────────────────────────

def save_cicd(data: dict) -> CICDPipeline:
    record = CICDPipeline(
        prompt=data["prompt"],
        tool_name=data["tool_name"],
        yaml_code=data["yaml_code"],
        explanation=data["explanation"],
        security_checks_json=json.dumps(data.get("security_checks", [])),
        model_used=data["model_used"],
    )
    with Session(engine) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def get_all_cicd() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(CICDPipeline).order_by(CICDPipeline.timestamp.desc())).all()
    return [_serialize_cicd(r) for r in rows]


def _serialize_cicd(r: CICDPipeline) -> dict:
    return {
        "id": r.id,
        "timestamp": r.timestamp.isoformat(),
        "prompt": r.prompt,
        "tool_name": r.tool_name,
        "yaml_code": r.yaml_code,
        "explanation": r.explanation,
        "security_checks": _safe_json_loads(r.security_checks_json),
        "model_used": r.model_used,
    }


# ── Settings ──────────────────────────────────────────────────────────────────

def get_settings() -> dict:
    with Session(engine) as session:
        rows = session.exec(select(UserSetting)).all()
    return {r.key: r.value for r in rows}


# ── Notifications ─────────────────────────────────────────────────────────────

def create_notification(message: str, type: str = "info", incident_id: int | None = None) -> Notification:
    n = Notification(message=message, type=type, incident_id=incident_id)
    with Session(engine) as session:
        session.add(n)
        session.commit()
        session.refresh(n)
    return n


def get_all_notifications() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(Notification).order_by(Notification.timestamp.desc()).limit(200)
        ).all()
    return [_serialize_notification(r) for r in rows]


def mark_notification_read(notification_id: int) -> dict | None:
    with Session(engine) as session:
        row = session.get(Notification, notification_id)
        if not row:
            return None
        row.is_read = True
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialize_notification(row)


def _serialize_notification(n: Notification) -> dict:
    return {
        "id":          n.id,
        "timestamp":   n.timestamp.isoformat(),
        "message":     n.message,
        "type":        n.type,
        "is_read":     n.is_read,
        "incident_id": n.incident_id,
    }


def update_settings(updates: dict) -> dict:
    with Session(engine) as session:
        for key, value in updates.items():
            row = session.exec(select(UserSetting).where(UserSetting.key == key)).first()
            if row:
                row.value = str(value)
                session.add(row)
            else:
                session.add(UserSetting(key=key, value=str(value)))
        session.commit()
    return get_settings()


# ── Webhook Events ─────────────────────────────────────────────────────────────

def save_webhook_event(data: dict) -> WebhookEvent:
    ev = WebhookEvent(
        source=data["source"],
        event_type=data.get("event_type", ""),
        owner_role=data.get("owner_role", "Admin"),
        status=data.get("status", "accepted"),
        incident_id=data.get("incident_id"),
        raw_payload=data.get("raw_payload", "{}"),
        cloud_event_id=data.get("cloud_event_id", ""),
    )
    with Session(engine) as session:
        session.add(ev)
        session.commit()
        session.refresh(ev)
    return ev


def update_webhook_event(event_id: int, status: str, incident_id: int | None = None):
    with Session(engine) as session:
        ev = session.get(WebhookEvent, event_id)
        if ev:
            ev.status = status
            if incident_id is not None:
                ev.incident_id = incident_id
            session.add(ev)
            session.commit()


def get_recent_webhook_events(limit: int = 40) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(WebhookEvent).order_by(WebhookEvent.timestamp.desc()).limit(limit)
        ).all()
    return [_serialize_webhook_event(r) for r in rows]


def _serialize_webhook_event(e: WebhookEvent) -> dict:
    return {
        "id":             e.id,
        "timestamp":      e.timestamp.isoformat(),
        "source":         e.source,
        "event_type":     e.event_type,
        "owner_role":     e.owner_role,
        "status":         e.status,
        "incident_id":    e.incident_id,
        "cloud_event_id": e.cloud_event_id,
    }
