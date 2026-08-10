"""Workflow definitions and runs API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..auth import User, get_current_user, require_admin, write_audit
from ..database import engine
from ..db.models.workflows import (
    VALID_CONCURRENT_LIMITS,
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
from ..services.workflow_triggers import (
    humanize_cron,
    next_fire_times,
    reload_schedule_jobs,
    set_triggers_enabled,
    triggers_status,
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
    on_concurrent_limit: str = "drop"
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


class KillSwitchBody(BaseModel):
    enabled: bool


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
    if body.on_concurrent_limit not in VALID_CONCURRENT_LIMITS:
        raise HTTPException(
            status_code=400,
            detail=f"on_concurrent_limit must be one of {sorted(VALID_CONCURRENT_LIMITS)}",
        )
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


def _reload_jobs_safe() -> None:
    try:
        reload_schedule_jobs()
    except Exception:
        pass


@router.get("")
def api_list_workflows(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    return list_definitions(tenant_id)


@router.get("/triggers/status")
def api_triggers_status(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    _ = require_tenant(request)
    _ = current_user
    return triggers_status()


@router.get("/triggers/preview")
def api_cron_preview(
    request: Request,
    cron: str = "",
    timezone: str = "UTC",
    current_user: User = Depends(get_current_user),
):
    _ = require_tenant(request)
    _ = current_user
    expr = (cron or "").strip()
    times = next_fire_times(expr, timezone_name=timezone or "UTC", count=5) if expr else []
    return {
        "cron": expr,
        "timezone": timezone or "UTC",
        "human": humanize_cron(expr) if expr else "",
        "next_fire_times": times,
    }


@router.post("/triggers/kill-switch")
def api_triggers_kill_switch(
    request: Request,
    body: KillSwitchBody,
    admin: User = Depends(require_admin),
):
    _ = require_tenant(request)
    enabled = set_triggers_enabled(bool(body.enabled), actor=admin.username)
    if enabled:
        _reload_jobs_safe()
    else:
        # Reload clears jobs when kill switch off
        _reload_jobs_safe()
    return triggers_status()


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
        on_concurrent_limit=body.on_concurrent_limit,
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
    _reload_jobs_safe()
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


@router.get("/{workflow_id}/trigger-preview")
def api_trigger_preview(
    request: Request,
    workflow_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = _get_definition(session, workflow_id, tenant_id)
        cfg = {}
        try:
            cfg = json.loads(row.trigger_config_json or "{}")
        except Exception:
            cfg = {}
        cron = str((cfg or {}).get("cron") or "").strip()
        tz_name = str((cfg or {}).get("timezone") or "UTC")
        times = next_fire_times(cron, timezone_name=tz_name, count=5) if cron else []
        return {
            "workflow_id": workflow_id,
            "trigger_type": row.trigger_type,
            "cron": cron,
            "timezone": tz_name,
            "human": humanize_cron(cron) if cron else "",
            "next_fire_times": times,
        }


@router.post("/{workflow_id}/approve-live")
def api_approve_live(
    request: Request,
    workflow_id: str,
    admin: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = _get_definition(session, workflow_id, tenant_id)
        row.first_live_run_approved_at = now
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        out = serialize_definition(row)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="workflow_live_approved",
        resource=f"workflow:{workflow_id}",
        detail=f"first_live_run_approved_at={now.isoformat()}",
    )
    return out


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
        old_steps = row.steps_json or "[]"
        new_steps = json.dumps(body.steps, default=str)
        steps_changed = parse_steps(old_steps) != parse_steps(new_steps)
        row.name = body.name.strip()
        row.description = body.description or ""
        row.steps_json = new_steps
        row.trigger_type = body.trigger_type
        row.trigger_config_json = json.dumps(body.trigger_config or {}, default=str)
        row.enabled = bool(body.enabled)
        row.risk = body.risk
        row.max_runs_per_hour = body.max_runs_per_hour
        row.max_concurrent_runs = body.max_concurrent_runs
        row.on_concurrent_limit = body.on_concurrent_limit
        row.workspace_id = body.workspace_id
        if steps_changed:
            row.first_live_run_approved_at = None
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
    _reload_jobs_safe()
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
    _reload_jobs_safe()
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
        automatic=False,
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


@runs_router.get("/{run_id}/export.pdf")
def api_export_run_pdf(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    from ..services.workflow_pdf import build_run_pdf
    from ..db.models.workflows import WorkflowRun

    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.get(WorkflowRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        assert_same_tenant(row.tenant_id, tenant_id)
        run = serialize_run(row, include_definition=True)
    definition = run.pop("workflow", None)
    pdf_bytes = build_run_pdf(run, definition)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="workflow-run-{run_id}.pdf"'},
    )


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
