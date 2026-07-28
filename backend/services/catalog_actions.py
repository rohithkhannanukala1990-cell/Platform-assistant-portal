"""Catalog self-service action execution (Phase G6)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, col, select

from ..auth import User
from ..db.core import engine
from ..db.models.ai_models import AgentRun
from ..db.models.catalog_actions import (
    ACTION_OPEN_INCIDENT,
    ACTION_PROPOSE_DEPLOY,
    ACTION_REQUEST_SCORECARD_REFRESH,
    ACTION_RUN_GOLDEN_PATH,
    CatalogAction,
)
from ..routers.catalog import CatalogEntity


def _parse_template(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def serialize_catalog_action(row: CatalogAction) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "entity_kind": row.entity_kind,
        "action_type": row.action_type,
        "payload_template": _parse_template(row.payload_template),
        "risk": row.risk,
        "require_hitl": bool(row.require_hitl),
        "tenant_id": row.tenant_id,
        "enabled": bool(row.enabled),
        "description": row.description or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_catalog_actions(
    *,
    tenant_id: str,
    entity_kind: str | None = None,
) -> list[dict[str, Any]]:
    with Session(engine) as session:
        q = select(CatalogAction).where(
            CatalogAction.enabled == True,  # noqa: E712
            CatalogAction.tenant_id == tenant_id,
        )
        rows = session.exec(q.order_by(col(CatalogAction.name))).all()
        out = []
        for row in rows:
            if entity_kind and row.entity_kind not in ("all", "", entity_kind):
                continue
            out.append(serialize_catalog_action(row))
        return out


def get_catalog_action(action_id: str, tenant_id: str) -> CatalogAction | None:
    with Session(engine) as session:
        row = session.get(CatalogAction, action_id)
        if not row or not row.enabled:
            return None
        if row.tenant_id and row.tenant_id != tenant_id:
            return None
        session.expunge(row)
        return row


def seed_catalog_actions(session: Session, tenant_id: str = "default") -> None:
    """Idempotent seed of built-in self-service actions."""
    builtins = [
        {
            "name": "Run Golden Path",
            "action_type": ACTION_RUN_GOLDEN_PATH,
            "entity_kind": "all",
            "risk": "medium",
            "require_hitl": False,
            "description": "Start an applicable golden path for this entity",
            "payload_template": json.dumps({"template_id": ""}),
        },
        {
            "name": "Refresh Scorecard",
            "action_type": ACTION_REQUEST_SCORECARD_REFRESH,
            "entity_kind": "all",
            "risk": "low",
            "require_hitl": False,
            "description": "Re-run evidence-based scorecard checks",
            "payload_template": "{}",
        },
        {
            "name": "Open Incident",
            "action_type": ACTION_OPEN_INCIDENT,
            "entity_kind": "all",
            "risk": "medium",
            "require_hitl": False,
            "description": "Create a portal incident linked to this entity",
            "payload_template": json.dumps({"severity": "High"}),
        },
        {
            "name": "Propose Deploy",
            "action_type": ACTION_PROPOSE_DEPLOY,
            "entity_kind": "Service",
            "risk": "high",
            "require_hitl": True,
            "description": "Propose a production deploy (requires HITL approval)",
            "payload_template": json.dumps({"environment": "production", "strategy": "rolling"}),
        },
    ]
    for item in builtins:
        exists = session.exec(
            select(CatalogAction).where(
                CatalogAction.tenant_id == tenant_id,
                CatalogAction.action_type == item["action_type"],
                CatalogAction.name == item["name"],
            )
        ).first()
        if exists:
            continue
        session.add(
            CatalogAction(
                id=str(uuid.uuid4()),
                name=item["name"],
                entity_kind=item["entity_kind"],
                action_type=item["action_type"],
                payload_template=item["payload_template"],
                risk=item["risk"],
                require_hitl=item["require_hitl"],
                tenant_id=tenant_id,
                enabled=True,
                description=item["description"],
            )
        )
    session.commit()


def _create_hitl_agent_run(
    *,
    user: User,
    action: CatalogAction,
    entity: CatalogEntity,
    payload: dict[str, Any],
    tenant_id: str,
) -> AgentRun:
    now = datetime.now(timezone.utc)
    run = AgentRun(
        id=str(uuid.uuid4()),
        agent="catalog_self_service",
        status="pending_approval",
        summary=f"HITL: {action.name} on {entity.name}",
        details_json=json.dumps(
            {
                "catalog_action_id": action.id,
                "action_type": action.action_type,
                "entity_id": entity.id,
                "entity_name": entity.name,
                "payload": payload,
                "risk": action.risk,
            },
            default=str,
        ),
        requires_approval=True,
        approval_payload_json=json.dumps(
            {
                "action": action.action_type,
                "entity_id": entity.id,
                "entity_name": entity.name,
                "payload": payload,
                "commands": [],
            },
            default=str,
        ),
        triggered_by=str(user.id) if user.id is not None else user.username,
        user_id=str(user.id) if user.id is not None else user.username,
        workspace_id=getattr(user, "workspace_id", None) or "",
        tenant_id=tenant_id,
        environment="production" if action.risk == "high" else "development",
        task=f"{action.action_type} entity={entity.id}",
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(run)
        session.commit()
        session.refresh(run)
        return run


async def _execute_run_golden_path(
    entity: CatalogEntity,
    payload: dict[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    from ..routers.golden_paths import (
        GoldenPathRun,
        GoldenPathTemplate,
        execute_golden_path_run,
        find_applicable_paths_for_entity,
    )

    template_id = payload.get("template_id")
    with Session(engine) as session:
        tpl: GoldenPathTemplate | None = None
        if template_id is not None and str(template_id).strip():
            try:
                tid = int(template_id)
            except (TypeError, ValueError):
                tid = None
            if tid is not None:
                tpl = session.get(GoldenPathTemplate, tid)
        if tpl is None:
            applicable = find_applicable_paths_for_entity(session, entity)
            if not applicable:
                return {
                    "ok": False,
                    "status": "failed",
                    "message": "No applicable golden path for this entity",
                }
            tpl = applicable[0]
        if not tpl or not tpl.is_active:
            return {"ok": False, "status": "failed", "message": "Golden path template not found"}

        now = datetime.now(timezone.utc)
        inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
        run = GoldenPathRun(
            template_id=tpl.id,
            template_name=tpl.name,
            entity_id=entity.id,
            requested_by=username,
            status="running",
            inputs_json=json.dumps(inputs),
            outputs_json="{}",
            run_logs="",
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run = await execute_golden_path_run(session, tpl, run)
        return {
            "ok": True,
            "status": run.status or "completed",
            "message": "Golden path started",
            "run_id": run.id,
            "template_id": tpl.id,
        }


async def _execute_scorecard_refresh(entity: CatalogEntity) -> dict[str, Any]:
    from ..routers.scorecards import evaluate_scorecard_evidence

    payload = await evaluate_scorecard_evidence(entity.id)
    return {
        "ok": True,
        "status": "completed",
        "message": "Scorecard refreshed",
        "overall_score": payload.get("overall_score"),
        "checks": len(payload.get("checks") or []),
    }


async def _execute_open_incident(
    entity: CatalogEntity,
    payload: dict[str, Any],
    *,
    tenant_id: str,
) -> dict[str, Any]:
    from ..database import save_incident

    severity = str(payload.get("severity") or "High")
    summary = str(payload.get("summary") or f"Incident opened for {entity.name}")
    inc = save_incident(
        {
            "severity": severity,
            "summary": summary,
            "root_cause": f"Opened via catalog self-service for {entity.kind} {entity.name}",
            "evidence": [f"entity_id={entity.id}", f"repo={entity.repo_url or 'n/a'}"],
            "action_plan": ["Triage entity health", "Notify owner team"],
            "commands": [],
            "raw_logs": f"catalog_action open_incident entity={entity.id}",
            "model_used": "catalog_action",
            "raw_response": "{}",
            "source": "catalog_action",
            "owner_role": "Admin",
            "tenant_id": tenant_id,
        }
    )
    return {
        "ok": True,
        "status": "completed",
        "message": f"Incident #{inc.id} created",
        "incident_id": inc.id,
    }


async def execute_catalog_action(
    *,
    action: CatalogAction,
    entity: CatalogEntity,
    user: User,
    tenant_id: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a catalog action; HITL-gated actions create a pending AgentRun."""
    template = _parse_template(action.payload_template)
    payload = {**template, **(inputs or {})}

    if action.require_hitl or action.action_type == ACTION_PROPOSE_DEPLOY:
        run = _create_hitl_agent_run(
            user=user,
            action=action,
            entity=entity,
            payload=payload,
            tenant_id=tenant_id,
        )
        return {
            "ok": True,
            "status": "pending_approval",
            "require_hitl": True,
            "message": f"Submitted for HITL approval ({action.name})",
            "agent_run_id": run.id,
            "action_type": action.action_type,
            "risk": action.risk,
        }

    if action.action_type == ACTION_RUN_GOLDEN_PATH:
        return await _execute_run_golden_path(entity, payload, username=user.username)
    if action.action_type == ACTION_REQUEST_SCORECARD_REFRESH:
        return await _execute_scorecard_refresh(entity)
    if action.action_type == ACTION_OPEN_INCIDENT:
        return await _execute_open_incident(entity, payload, tenant_id=tenant_id)

    return {
        "ok": False,
        "status": "failed",
        "message": f"Unknown action_type={action.action_type}",
    }
