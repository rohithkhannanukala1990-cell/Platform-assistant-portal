import json
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session, select

DATABASE_URL = "sqlite:///./incidents.db"
engine = create_engine(DATABASE_URL, echo=False)


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
    source: str = Field(default="manual")   # "manual" | "webhook:<source-name>"


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


def _migrate():
    """Add columns that were introduced after the initial schema."""
    from sqlalchemy import text
    migrations = [
        ("incident",     "source",    "TEXT",    "'manual'"),
        ("notification", "incident_id","INTEGER", "NULL"),
    ]
    with Session(engine) as session:
        for table, col, col_type, default in migrations:
            try:
                rows = session.exec(text(f"PRAGMA table_info({table})")).all()
                existing = [r[1] for r in rows]
                if col not in existing:
                    session.exec(text(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}"
                    ))
                    session.commit()
            except Exception as exc:
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
        raw_logs=data["raw_logs"],
        model_used=data["model_used"],
        raw_response=data["raw_response"],
        source=data.get("source", "manual"),
    )
    with Session(engine) as session:
        session.add(incident)
        session.commit()
        session.refresh(incident)
    return incident


def get_all_incidents() -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(select(Incident).order_by(Incident.timestamp.desc())).all()
    return [_serialize_incident(r) for r in rows]


def _serialize_incident(i: Incident) -> dict:
    return {
        "id": i.id,
        "timestamp": i.timestamp.isoformat(),
        "severity": i.severity,
        "summary": i.summary,
        "root_cause": i.root_cause,
        "evidence": json.loads(i.evidence_json),
        "action_plan": json.loads(i.action_plan_json),
        "commands": json.loads(i.commands_json),
        "files_to_check": json.loads(i.files_to_check_json),
        "validation_steps": json.loads(i.validation_steps_json),
        "raw_logs": i.raw_logs,
        "model_used": i.model_used,
        "raw_response": i.raw_response,
        "source": getattr(i, "source", "manual") or "manual",
    }


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
        "cli_commands": json.loads(r.cli_commands_json),
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
        "security_checks": json.loads(r.security_checks_json),
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
        rows = session.exec(select(Notification).order_by(Notification.timestamp.desc())).all()
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
