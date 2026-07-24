"""Agent pipeline API — run, list, approvals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from ..agents import get_agent, list_agents, AgentNotFound
from ..agents.base import AgentResult
from ..auth import AuditLog, User, get_current_user, write_audit
from ..context import PlatformContext
from ..database import AgentRun, UserContext, engine
from ..executor.safe_executor import safe_executor
from ..pipeline.orchestrator import orchestrator_agent
from ..rate_limit import limiter

router = APIRouter(prefix="/api/agents", tags=["agents"])


class RunAgentRequest(BaseModel):
    task: str
    context: dict = Field(default_factory=dict)
    override_agents: Optional[list[str]] = None


def _session():
    with Session(engine) as session:
        yield session


def _role_for_user(user: User) -> str:
    return "Admin" if (user.role or "").strip() == "Admin" else "User"


def _load_user_tool_accounts(session: Session, user: User) -> dict[str, str]:
    uid = str(user.id) if getattr(user, "id", None) is not None else str(user.username)
    row = session.get(UserContext, uid)
    if row is None and user.username:
        row = session.get(UserContext, user.username)
    if not row or not row.active_accounts:
        return {}
    try:
        mapping = json.loads(row.active_accounts or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(mapping, dict):
        return {}
    return {str(k): str(v) for k, v in mapping.items() if k and v}


def _build_platform_context(
    request: Request,
    body: RunAgentRequest,
    current_user: User,
) -> PlatformContext:
    """Always stamp authenticated user + workspace/tenant + UserContext pins."""
    state_ws = getattr(request.state, "workspace_id", None)
    state_tenant = getattr(request.state, "tenant_id", None)
    body_ctx = body.context if isinstance(body.context, dict) else {}

    with Session(engine) as session:
        pinned = _load_user_tool_accounts(session, current_user)

    merged_accounts = {**pinned}
    body_accounts = body_ctx.get("tool_accounts") or {}
    if isinstance(body_accounts, dict):
        # Client may narrow pins; never inject foreign account ids without pin ownership checks later.
        merged_accounts.update({str(k): str(v) for k, v in body_accounts.items() if k and v})

    uid = str(current_user.id) if current_user.id is not None else str(current_user.username)
    workspace_id = (
        body_ctx.get("workspace_id")
        or state_ws
        or getattr(current_user, "workspace_id", None)
    )
    tenant_id = (
        body_ctx.get("tenant_id")
        or state_tenant
        or getattr(current_user, "tenant_id", None)
        or "default"
    )
    payload = {
        **body_ctx,
        "user_id": uid,
        "user_role": _role_for_user(current_user),
        "workspace_id": workspace_id,
        "tenant_id": tenant_id,
        "tool_accounts": merged_accounts,
    }
    return PlatformContext.from_dict(
        payload,
        user_id=uid,
        user_role=_role_for_user(current_user),
    )


def _run_to_dict(row: AgentRun) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "agent": row.agent,
        "status": row.status,
        "summary": row.summary,
        "details": json.loads(row.details_json or "{}"),
        "requires_approval": row.requires_approval,
        "approval_payload": json.loads(row.approval_payload_json or "{}"),
        "execution_log": row.execution_log,
        "triggered_by": row.triggered_by,
        "workspace": row.workspace_id,
        "environment": row.environment,
        "timestamp": row.created_at.isoformat() if row.created_at else "",
        "task": row.task,
    }


@router.get("/")
def list_all_agents(current_user: User = Depends(get_current_user)):
    return list_agents()


@router.post("/run")
@limiter.limit("10/minute")
async def run_agent(
    request: Request,
    body: RunAgentRequest,
    current_user: User = Depends(get_current_user),
):
    ctx = _build_platform_context(request, body, current_user)
    with Session(engine) as session:
        result = await orchestrator_agent.run(
            body.task,
            ctx,
            session,
            override_agents=body.override_agents,
        )
    return result.to_dict()


@router.get("/approvals")
def list_approvals(
    workspace_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        q = select(AgentRun).where(AgentRun.status == "pending_approval")
        if workspace_id:
            q = q.where(AgentRun.workspace_id == workspace_id)
        rows = session.exec(q.order_by(AgentRun.created_at.desc())).all()
    return [_run_to_dict(r) for r in rows]


@router.get("/runs")
def list_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Paginated agent run history with optional status and workspace filters."""
    with Session(engine) as session:
        q = select(AgentRun)
        count_q = select(func.count()).select_from(AgentRun)
        if status:
            q = q.where(AgentRun.status == status.strip().lower())
            count_q = count_q.where(AgentRun.status == status.strip().lower())
        if workspace_id:
            q = q.where(AgentRun.workspace_id == workspace_id)
            count_q = count_q.where(AgentRun.workspace_id == workspace_id)
        total = int(session.exec(count_q).one() or 0)
        rows = session.exec(
            q.order_by(AgentRun.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "items": [_run_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }


@router.get("/{agent_name}")
def get_agent_meta(
    agent_name: str,
    current_user: User = Depends(get_current_user),
):
    if agent_name == "approvals":
        return list_approvals(None, current_user)
    try:
        agent = get_agent(agent_name)
    except AgentNotFound:
        raise HTTPException(status_code=404, detail="Agent not found")

    with Session(engine) as session:
        logs = session.exec(
            select(AuditLog)
            .where(AuditLog.resource == agent_name)
            .order_by(AuditLog.timestamp.desc())
            .limit(10)
        ).all()

    return {
        "name": agent.name,
        "description": agent.description,
        "requires_approval_envs": agent.requires_approval_envs,
        "primary_tools": agent.primary_tools,
        "recent_audit": [
            {
                "timestamp": l.timestamp.isoformat(),
                "actor": l.actor,
                "event_type": l.event_type,
                "detail": l.detail,
            }
            for l in logs
        ],
    }


@router.post("/{run_id}/approve")
@limiter.limit("10/minute")
async def approve_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        if row.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Run is not pending approval")

        payload = json.loads(row.approval_payload_json or "{}")
        commands = payload.get("commands") or []
        if not commands and isinstance(payload.get("agents"), list):
            for sub in payload["agents"]:
                commands.extend(sub.get("details", {}).get("commands") or [])

        exec_log = None
        if commands:
            out = await safe_executor.execute(
                commands, incident_id=0, approved_by=current_user.username
            )
            exec_log = out.get("logs")
            row.status = "success" if out.get("success") else "failed"
        else:
            row.status = "success"

        row.execution_log = exec_log
        row.requires_approval = False
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()

        write_audit(
            current_user.username,
            current_user.role,
            "agent_approved",
            resource=row.agent,
            detail=row.id,
        )
        return _run_to_dict(row)


@router.post("/{run_id}/reject")
@limiter.limit("10/minute")
def reject_run(
    request: Request,
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        row.status = "failed"
        row.requires_approval = False
        row.summary = f"Rejected by {current_user.username}: {row.summary}"
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        write_audit(
            current_user.username,
            current_user.role,
            "agent_rejected",
            resource=row.agent,
            detail=row.id,
        )
        return _run_to_dict(row)
