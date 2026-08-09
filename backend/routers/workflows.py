"""Workflow definitions and runs API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..auth import User, get_current_user, require_admin, write_audit
from ..database import engine
from ..db.models.workflows import (
    VALID_RISKS,
    VALID_TRIGGER_TYPES,
    WorkflowDefinition,
)
from ..services.isolation import assert_same_tenant, require_tenant
from ..services.workflow_engine import (
    WorkflowValidationError,
    advance_workflow,
    cancel_workflow,
    list_definitions,
    list_runs,
    parse_steps,
    reject_workflow,
    resume_after_approval,
    serialize_definition,
    serialize_run,
    start_workflow,
    validate_workflow_steps,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])
runs_router = APIRouter(prefix="/api/workflows/runs", tags=["workflow-runs"])


class WorkflowBody(BaseModel):
    name: str
    description: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    trigger_type: str = "manual"
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    risk: str = "medium"
    max_runs_per_hour: int = 12
    max_concurrent_runs: int = 1
    workspace_id: Optional[str] = None


class ValidateBody(BaseModel):
    steps: list[dict[str, Any]] = Field(default_factory=list)


class RunBody(BaseModel):
    dry_run: bool = False
    context: dict[str, Any] = Field(default_factory=dict)


class ApproveBody(BaseModel):
    step_id: Optional[str] = None


class RejectBody(BaseModel):
    step_id: Optional[str] = None
    reason: str = ""


def _validate_meta(body: WorkflowBody) -> None:
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.trigger_type not in VALID_TRIGGER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"trigger_type must be one of {sorted(VALID_TRIGGER_TYPES)}",
        )
    if body.risk not in VALID_RISKS:
        raise HTTPException(status_code=400, detail=f"risk must be one of {sorted(VALID_RISKS)}")
    if body.max_runs_per_hour < 1:
        raise HTTPException(status_code=400, detail="max_runs_per_hour must be >= 1")
    if body.max_concurrent_runs < 1:
        raise HTTPException(status_code=400, detail="max_concurrent_runs must be >= 1")
    errors = validate_workflow_steps(body.steps)
    if errors:
        raise HTTPException(status_code=422, detail=errors)


def _get_definition(session: Session, workflow_id: str, tenant_id: str) -> WorkflowDefinition:
    row = session.get(WorkflowDefinition, workflow_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    assert_same_tenant(row.tenant_id, tenant_id)
    return row


@router.get("")
def api_list_workflows(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    return list_definitions(tenant_id)


@router.post("", status_code=201)
def api_create_workflow(
    request: Request,
    body: WorkflowBody,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    _validate_meta(body)
    now = datetime.now(timezone.utc)
    row = WorkflowDefinition(
        tenant_id=tenant_id,
        workspace_id=body.workspace_id,
        name=body.name.strip(),
        description=body.description or "",
        steps_json=json.dumps(body.steps, default=str),
        trigger_type=body.trigger_type,
        trigger_config_json=json.dumps(body.trigger_config or {}, default=str),
        enabled=bool(body.enabled),
        risk=body.risk,
        max_runs_per_hour=body.max_runs_per_hour,
        max_concurrent_runs=body.max_concurrent_runs,
        created_by=admin.username,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        out = serialize_definition(row)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="workflow_created",
        resource=f"workflow:{out['id']}",
        detail=body.name,
    )
    return out


@router.post("/validate")
def api_validate_workflow(
    request: Request,
    body: ValidateBody,
    current_user: User = Depends(get_current_user),
):
    _ = require_tenant(request)
    errors = validate_workflow_steps(body.steps or [])
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"ok": True, "errors": []}


@router.get("/{workflow_id}")
def api_get_workflow(
    request: Request,
    workflow_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = _get_definition(session, workflow_id, tenant_id)
        return serialize_definition(row)


@router.put("/{workflow_id}")
def api_update_workflow(
    request: Request,
    workflow_id: str,
    body: WorkflowBody,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    _validate_meta(body)
    with Session(engine) as session:
        row = _get_definition(session, workflow_id, tenant_id)
        row.name = body.name.strip()
        row.description = body.description or ""
        row.steps_json = json.dumps(body.steps, default=str)
        row.trigger_type = body.trigger_type
        row.trigger_config_json = json.dumps(body.trigger_config or {}, default=str)
        row.enabled = bool(body.enabled)
        row.risk = body.risk
        row.max_runs_per_hour = body.max_runs_per_hour
        row.max_concurrent_runs = body.max_concurrent_runs
        row.workspace_id = body.workspace_id
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        out = serialize_definition(row)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="workflow_updated",
        resource=f"workflow:{workflow_id}",
        detail=body.name,
    )
    return out


@router.delete("/{workflow_id}", status_code=204)
def api_delete_workflow(
    request: Request,
    workflow_id: str,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = _get_definition(session, workflow_id, tenant_id)
        session.delete(row)
        session.commit()
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="workflow_deleted",
        resource=f"workflow:{workflow_id}",
        detail="",
    )
    return None


@router.post("/{workflow_id}/run")
async def api_run_workflow(
    request: Request,
    workflow_id: str,
    body: RunBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        _get_definition(session, workflow_id, tenant_id)
    run = await start_workflow(
        workflow_id,
        tenant_id,
        triggered_by=current_user.username,
        initial_context=body.context or {},
        dry_run=bool(body.dry_run),
    )
    return serialize_run(run)


@router.post("/{workflow_id}/validate")
def api_validate_workflow_by_id(
    request: Request,
    workflow_id: str,
    body: ValidateBody,
    current_user: User = Depends(get_current_user),
):
    """Validate supplied steps (or stored definition if steps empty)."""
    tenant_id = require_tenant(request)
    steps = body.steps
    if not steps:
        with Session(engine) as session:
            row = _get_definition(session, workflow_id, tenant_id)
            steps = parse_steps(row.steps_json)
    errors = validate_workflow_steps(steps or [])
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"ok": True, "errors": []}


@runs_router.get("")
def api_list_runs(
    request: Request,
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return list_runs(tenant_id, status=status, workflow_id=workflow_id)


@runs_router.get("/{run_id}")
def api_get_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        from ..db.models.workflows import WorkflowRun

        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        assert_same_tenant(row.tenant_id, tenant_id)
        return serialize_run(row, include_definition=True)


@runs_router.post("/{run_id}/approve")
async def api_approve_run(
    request: Request,
    run_id: str,
    body: ApproveBody,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        from ..db.models.workflows import WorkflowRun

        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        assert_same_tenant(row.tenant_id, tenant_id)
        step_id = body.step_id or row.current_step_id or ""
    run = await resume_after_approval(
        run_id,
        step_id,
        approved_by=admin.username,
        tenant_id=tenant_id,
    )
    return serialize_run(run)


@runs_router.post("/{run_id}/reject")
async def api_reject_run(
    request: Request,
    run_id: str,
    body: RejectBody,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        from ..db.models.workflows import WorkflowRun

        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        assert_same_tenant(row.tenant_id, tenant_id)
        step_id = body.step_id or row.current_step_id or ""
    run = await reject_workflow(
        run_id,
        step_id,
        rejected_by=admin.username,
        reason=body.reason or "Rejected",
        tenant_id=tenant_id,
    )
    return serialize_run(run)


@runs_router.post("/{run_id}/cancel")
async def api_cancel_run(
    request: Request,
    run_id: str,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        from ..db.models.workflows import WorkflowRun

        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        assert_same_tenant(row.tenant_id, tenant_id)
    run = await cancel_workflow(run_id, cancelled_by=admin.username, tenant_id=tenant_id)
    return serialize_run(run)


# Re-export for tests / callers that want to poke advance directly
__all__ = ["router", "runs_router", "advance_workflow", "WorkflowValidationError"]
