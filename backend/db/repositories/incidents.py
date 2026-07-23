"""Incident CRUD, serialization, and approval queries."""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..core import engine
from ..models.ops import Incident


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


def list_incidents(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
) -> list[dict]:
    limit = max(1, min(int(limit or 100), 500))
    offset = max(0, int(offset or 0))
    with Session(engine) as session:
        q = select(Incident).order_by(Incident.timestamp.desc())
        if status:
            q = q.where(Incident.status == status)
        rows = session.exec(q.offset(offset).limit(limit)).all()
    return [serialize_incident(r) for r in rows]


def get_all_incidents() -> list[dict]:
    """Deprecated wrapper — prefer list_incidents(limit=..., offset=..., status=...)."""
    return list_incidents(limit=500)


def _serialize_incident(i: Incident) -> dict:
    return serialize_incident(i)


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
        "source": getattr(i, "source", "manual") or "manual",
        "status": getattr(i, "status", "OPEN") or "OPEN",
        "execution_logs": getattr(i, "execution_logs", None),
        "owner_role": getattr(i, "owner_role", "Admin") or "Admin",
        "proposed_remediation_plan": _safe_json_loads(
            getattr(i, "proposed_remediation_plan", None)
        ),
        "agent_execution_logs": getattr(i, "agent_execution_logs", None),
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


__all__ = [
    "save_incident",
    "list_incidents",
    "get_all_incidents",
    "serialize_incident",
    "_serialize_incident",
    "_safe_json_loads",
    "update_incident_status",
    "get_pending_approvals",
]
