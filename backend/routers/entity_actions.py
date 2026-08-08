"""Entity actions — contextual self-service operations per catalog entity."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user, require_admin
from ..database import engine
from .audit_log import log_audit_event
from .catalog import CatalogEntity
from .rbac import TRIGGER_ENTITY_ACTION, require_capability
from ..services.isolation import assert_same_tenant, require_tenant

router = APIRouter(prefix="/api/entity-actions", tags=["entity-actions"])
catalog_router = APIRouter(prefix="/api/catalog", tags=["entity-actions"])
runs_router = APIRouter(prefix="/api/entity-action-runs", tags=["entity-actions"])


class EntityAction(SQLModel, table=True):
    __tablename__ = "entity_actions"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    slug: str
    description: str = ""
    entity_kind: str = "all"
    action_type: str = "internal"
    icon: str = "Zap"
    config_json: str = "{}"
    requires_approval: int = 0
    is_active: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EntityActionRun(SQLModel, table=True):
    __tablename__ = "entity_action_runs"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    action_id: str = Field(foreign_key="entity_actions.id", index=True)
    entity_id: str = Field(foreign_key="catalog_entities.id", index=True)
    requested_by: str
    status: str = "pending"
    inputs_json: str = "{}"
    result_json: str = "{}"
    execution_logs: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EntityActionCreate(BaseModel):
    name: str
    slug: str
    description: str = ""
    entity_kind: str = "all"
    action_type: str = "internal"
    icon: str = "Zap"
    config_json: str = "{}"
    requires_approval: int = 0


class ActionRunRequest(BaseModel):
    inputs_json: Optional[dict[str, Any]] = None


def _get_active_entity(
    session: Session, entity_id: str, *, tenant_id: str | None = None
) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    if tenant_id is not None:
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
    return row


def _log_line(logs: list[str], message: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    logs.append(f"[{ts}] {message}")


def _serialize_action(row: EntityAction) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description or "",
        "entity_kind": row.entity_kind,
        "action_type": row.action_type,
        "icon": row.icon,
        "config_json": row.config_json,
        "requires_approval": bool(row.requires_approval),
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_run(row: EntityActionRun, action_name: str | None = None) -> dict[str, Any]:
    try:
        result = json.loads(row.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    try:
        inputs = json.loads(row.inputs_json or "{}")
    except json.JSONDecodeError:
        inputs = {}
    return {
        "id": row.id,
        "action_id": row.action_id,
        "action_name": action_name,
        "entity_id": row.entity_id,
        "requested_by": row.requested_by,
        "status": row.status,
        "inputs": inputs,
        "result": result,
        "execution_logs": row.execution_logs or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


_NOT_IMPLEMENTED = {
    "status": "not_implemented",
    "message": (
        "This action type is not yet wired to a live handler. "
        "Connect the relevant integration in Settings → Tool Registry "
        "to enable real execution."
    ),
}


async def _run_internal_action(
    session: Session, action: EntityAction, entity: CatalogEntity, logs: list[str]
) -> dict[str, Any]:
    slug = action.slug

    if slug == "re-eval-scorecard":
        from .scorecards import evaluate_scorecard_evidence

        _log_line(logs, "Invoking evidence-based scorecard evaluation")
        payload = await evaluate_scorecard_evidence(entity.id)
        _log_line(logs, f"Scorecard updated with {len(payload.get('checks') or [])} checks")
        return {"message": "Scorecard re-evaluated", "overall_score": payload.get("overall_score")}

    if slug == "flag-prod-readiness":
        from .standards import Standard, _run_evaluation

        std = session.exec(select(Standard).where(Standard.slug == "prod-readiness-v1")).first()
        if not std:
            _log_line(logs, "Production readiness standard not found")
            return {
                **_NOT_IMPLEMENTED,
                "message": "Production readiness standard is not seeded in this environment.",
            }
        ev = _run_evaluation(session, entity, std)
        _log_line(logs, f"Standards evaluation status={ev.status} score={ev.overall_score}")
        return {
            "message": "Production readiness evaluation complete",
            "overall_score": ev.overall_score,
            "status": ev.status,
        }

    if slug in ("generate-cicd", "generate-infra", "create-jira-ticket"):
        _log_line(logs, f"Internal handler for {slug} not wired")
        return dict(_NOT_IMPLEMENTED)

    _log_line(logs, "No specific handler registered for this action")
    return dict(_NOT_IMPLEMENTED)


async def _dispatch_action(
    session: Session,
    action: EntityAction,
    entity: CatalogEntity,
    logs: list[str],
    *,
    force_execute: bool = False,
) -> tuple[str, dict[str, Any]]:
    if not force_execute and (action.action_type == "approval" or action.requires_approval):
        _log_line(logs, "Awaiting approval")
        return "pending", {"message": "Submitted for approval"}

    if action.action_type == "webhook":
        _log_line(logs, "Webhook action has no live delivery handler")
        return "not_implemented", dict(_NOT_IMPLEMENTED)

    if action.action_type in ("internal", "approval") or force_execute:
        _log_line(logs, f"Running internal action: {action.slug}")
        result = await _run_internal_action(session, action, entity, logs)
        if result.get("status") == "not_implemented":
            return "not_implemented", result
        return "completed", result

    _log_line(logs, f"No handler for action_type={action.action_type}")
    return "not_implemented", {
        "status": "not_implemented",
        "message": f"No handler registered for action_type='{action.action_type}'.",
    }


def _audit_action_run(
    user: User,
    action: EntityAction,
    entity: CatalogEntity,
    run: EntityActionRun,
    inputs: dict[str, Any],
) -> None:
    """Central audit hook for action runs — covers every dispatch path."""
    log_audit_event(
        user,
        action.slug or "entity_action_run",
        entity.id,
        details={
            "run_id": run.id,
            "action_id": action.id,
            "action_name": action.name,
            "action_type": action.action_type,
            "entity_name": entity.name,
            "entity_kind": entity.kind,
            "entity_lifecycle": entity.lifecycle,
            "inputs": inputs,
        },
        status=run.status,
    )


def seed_default_actions(session: Session) -> None:
    defaults = [
        ("Re-evaluate Scorecard", "re-eval-scorecard", "all", "internal", "RefreshCw", 0),
        ("Generate CI/CD Config", "generate-cicd", "Service", "internal", "GitBranch", 0),
        ("Generate Infra Scaffold", "generate-infra", "Service", "internal", "Server", 1),
        ("Request Production Access", "request-prod-access", "all", "approval", "KeyRound", 1),
        ("Create Jira Ticket", "create-jira-ticket", "all", "internal", "Ticket", 0),
        ("Flag for Production Readiness", "flag-prod-readiness", "all", "internal", "ShieldCheck", 0),
    ]
    for name, slug, kind, atype, icon, approval in defaults:
        exists = session.exec(select(EntityAction).where(EntityAction.slug == slug)).first()
        if exists:
            continue
        session.add(
            EntityAction(
                id=str(uuid.uuid4()),
                name=name,
                slug=slug,
                description=f"Default action: {name}",
                entity_kind=kind,
                action_type=atype,
                icon=icon,
                requires_approval=approval,
                is_active=1,
                created_at=datetime.now(timezone.utc),
            )
        )
    session.commit()


@router.get("")
def list_entity_actions(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(
            select(EntityAction).where(EntityAction.is_active == 1).order_by(EntityAction.name)
        ).all()
        return [_serialize_action(r) for r in rows]


@router.post("")
def create_entity_action(body: EntityActionCreate, current_user: User = Depends(require_admin)):
    with Session(engine) as session:
        dup = session.exec(select(EntityAction).where(EntityAction.slug == body.slug.strip())).first()
        if dup:
            raise HTTPException(status_code=400, detail="Action slug already exists")
        row = EntityAction(
            id=str(uuid.uuid4()),
            name=body.name.strip(),
            slug=body.slug.strip(),
            description=(body.description or "").strip(),
            entity_kind=(body.entity_kind or "all").strip(),
            action_type=(body.action_type or "internal").strip(),
            icon=(body.icon or "Zap").strip(),
            config_json=body.config_json or "{}",
            requires_approval=int(body.requires_approval or 0),
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        log_audit_event(
            current_user,
            "entity_action_created",
            row.id,
            details={
                "name": row.name,
                "slug": row.slug,
                "entity_kind": row.entity_kind,
                "action_type": row.action_type,
                "requires_approval": bool(row.requires_approval),
            },
            resource_type="entity_action",
        )
        return _serialize_action(row)


@catalog_router.get("/{entity_id}/actions")
def list_applicable_actions(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        entity = _get_active_entity(session, entity_id, tenant_id=tenant_id)
        rows = session.exec(select(EntityAction).where(EntityAction.is_active == 1)).all()
        applicable = [
            _serialize_action(a)
            for a in rows
            if a.entity_kind in ("all", "") or a.entity_kind == entity.kind
        ]
        return applicable


@catalog_router.post("/{entity_id}/actions/{action_id}/run")
async def run_entity_action(
    request: Request,
    entity_id: str,
    action_id: str,
    body: ActionRunRequest | None = None,
    current_user: User = Depends(require_capability(TRIGGER_ENTITY_ACTION)),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        entity = _get_active_entity(session, entity_id, tenant_id=tenant_id)
        action = session.get(EntityAction, action_id)
        if not action or not action.is_active:
            raise HTTPException(status_code=404, detail="Action not found")
        if action.entity_kind not in ("all", "") and action.entity_kind != entity.kind:
            raise HTTPException(status_code=400, detail="Action not applicable to this entity kind")

        now = datetime.now(timezone.utc)
        logs: list[str] = []
        _log_line(logs, f"Run requested by {current_user.username}")

        inputs = body.inputs_json if body and body.inputs_json else {}
        run = EntityActionRun(
            id=str(uuid.uuid4()),
            action_id=action.id,
            entity_id=entity.id,
            requested_by=current_user.username,
            status="running",
            inputs_json=json.dumps(inputs),
            result_json="{}",
            execution_logs="",
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        session.commit()

        try:
            final_status, result = await _dispatch_action(session, action, entity, logs)
        except Exception as exc:
            final_status = "failed"
            result = {"error": str(exc)}
            _log_line(logs, f"Execution failed: {exc}")

        _log_line(logs, f"Run finished with status={final_status}")
        run.status = final_status
        run.result_json = json.dumps(result)
        run.execution_logs = "\n".join(logs)
        run.updated_at = datetime.now(timezone.utc)
        session.add(run)
        session.commit()
        session.refresh(run)

        _audit_action_run(current_user, action, entity, run, inputs)

        from ..ws_portal import broadcast_json

        asyncio.create_task(
            broadcast_json(
                {
                    "type": "entity_action_run_update",
                    "run_id": str(run.id),
                    "action_id": str(run.action_id),
                    "status": run.status,
                    "entity_id": str(run.entity_id) if run.entity_id else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        )

        return _serialize_run(run, action_name=action.name)


@runs_router.get("")
def list_action_runs(
    request: Request,
    entity_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        q = (
            select(EntityActionRun)
            .join(CatalogEntity, CatalogEntity.id == EntityActionRun.entity_id)
            .where(CatalogEntity.tenant_id == tenant_id)
            .order_by(EntityActionRun.created_at.desc())
        )
        if entity_id:
            _get_active_entity(session, entity_id, tenant_id=tenant_id)
            q = q.where(EntityActionRun.entity_id == entity_id)
        rows = session.exec(q).all()
        out = []
        for r in rows:
            action = session.get(EntityAction, r.action_id)
            out.append(_serialize_run(r, action_name=action.name if action else None))
        return out


@runs_router.get("/{run_id}")
def get_action_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.get(EntityActionRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        _get_active_entity(session, row.entity_id, tenant_id=tenant_id)
        action = session.get(EntityAction, row.action_id)
        return _serialize_run(row, action_name=action.name if action else None)


@runs_router.post("/{run_id}/approve")
async def approve_entity_action_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(require_admin),
):
    """HITL approve — re-dispatch the real action instead of only flipping status."""
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.get(EntityActionRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Action run not found")
        entity = _get_active_entity(session, row.entity_id, tenant_id=tenant_id)
        if row.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Run is not pending approval, status={row.status}",
            )

        action = session.get(EntityAction, row.action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")

        logs: list[str] = []
        _log_line(logs, f"Approved by {current_user.username} — re-dispatching")
        try:
            final_status, result = await _dispatch_action(
                session, action, entity, logs, force_execute=True
            )
        except Exception as exc:
            final_status = "failed"
            result = {"error": str(exc)}
            _log_line(logs, f"Post-approval execution failed: {exc}")

        now = datetime.now(timezone.utc)
        result = {
            **(result or {}),
            "approved_by": current_user.username,
            "approved_at": now.isoformat(),
        }
        _log_line(logs, f"Run finished with status={final_status}")
        row.status = final_status
        row.result_json = json.dumps(result)
        row.execution_logs = "\n".join(
            [*(row.execution_logs.splitlines() if row.execution_logs else []), *logs]
        )
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)

        try:
            inputs = json.loads(row.inputs_json or "{}")
        except json.JSONDecodeError:
            inputs = {}
        _audit_action_run(current_user, action, entity, row, inputs)
        return _serialize_run(row, action_name=action.name)


@runs_router.post("/{run_id}/reject")
def reject_entity_action_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.get(EntityActionRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Action run not found")
        entity = _get_active_entity(session, row.entity_id, tenant_id=tenant_id)
        if row.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Run is not pending approval, status={row.status}",
            )
        action = session.get(EntityAction, row.action_id)
        now = datetime.now(timezone.utc)
        row.status = "failed"
        row.result_json = json.dumps(
            {
                "status": "rejected",
                "rejected_by": current_user.username,
                "rejected_at": now.isoformat(),
            }
        )
        row.execution_logs = (row.execution_logs or "") + f"\n[{now.isoformat()}] Rejected by {current_user.username}"
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        try:
            inputs = json.loads(row.inputs_json or "{}")
        except json.JSONDecodeError:
            inputs = {}
        if action:
            _audit_action_run(current_user, action, entity, row, inputs)
        return _serialize_run(row, action_name=action.name if action else None)
