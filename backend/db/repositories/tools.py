"""Tool connections plus infra / CI/CD generation history helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from ..core import engine
from ..models.ops import CICDPipeline, InfraGeneration
from ..models.tools import ToolConnection
from .incidents import _safe_json_loads


def get_tool_connections(
    session: Session, workspace_id: str, tool_id: str | None = None
) -> list[ToolConnection]:
    q = select(ToolConnection).where(ToolConnection.workspace_id == workspace_id)
    if tool_id:
        q = q.where(ToolConnection.tool_id == tool_id)
    return list(session.exec(q).all())


def get_tool_connection(
    session: Session, workspace_id: str, tool_id: str, account_alias: str
) -> ToolConnection | None:
    return session.exec(
        select(ToolConnection).where(
            ToolConnection.workspace_id == workspace_id,
            ToolConnection.tool_id == tool_id,
            ToolConnection.account_alias == account_alias,
        )
    ).first()


def create_tool_connection(session: Session, **kwargs) -> ToolConnection:
    row = ToolConnection(**kwargs)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_tool_connection_status(session: Session, connection_id: str, status: str) -> None:
    row = session.get(ToolConnection, connection_id)
    if not row:
        return
    row.status = status
    row.last_tested_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    session.add(row)
    session.commit()


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


def list_infra(limit: int = 50, offset: int = 0) -> list[dict]:
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    with Session(engine) as session:
        rows = session.exec(
            select(InfraGeneration)
            .order_by(InfraGeneration.timestamp.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    return [_serialize_infra(r) for r in rows]


def get_all_infra() -> list[dict]:
    return list_infra(limit=200, offset=0)


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


def list_cicd(limit: int = 50, offset: int = 0) -> list[dict]:
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, int(offset or 0))
    with Session(engine) as session:
        rows = session.exec(
            select(CICDPipeline)
            .order_by(CICDPipeline.timestamp.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    return [_serialize_cicd(r) for r in rows]


def get_all_cicd() -> list[dict]:
    return list_cicd(limit=200, offset=0)


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


__all__ = [
    "get_tool_connections",
    "get_tool_connection",
    "create_tool_connection",
    "update_tool_connection_status",
    "save_infra",
    "list_infra",
    "get_all_infra",
    "_serialize_infra",
    "save_cicd",
    "list_cicd",
    "get_all_cicd",
    "_serialize_cicd",
]
