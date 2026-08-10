"""Unified approvals inbox — aggregates every pending-human-decision source into
one normalized shape, and dispatches approve/reject to the existing, per-source
service function. This module holds no approval logic of its own: every branch
below calls a function that already exists (or a thin extraction/reject-mirror
added alongside this file) so the inbox and the Slack receiver share one code
path with every other approval surface in the app.

Sources (confirmed by exploring the codebase — see Sprint 6 plan):
  agent          AgentRun (status=pending_approval) — covers generic agent runs,
                 catalog actions, terminal commands, artifact write-back, editor PRs
  workflow       WorkflowRun (status=pending_approval)
  mcp            MCPToolCall (status=pending_approval)
  entity_action  EntityActionRun (status=pending) — tenant-scoped via CatalogEntity
  access         AccessRequestRecord (status=pending_approval)
  change         ChangeRecord (status in draft/submitted)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select

from ..auth import User
from ..database import AgentRun, engine
from ..db.models.access import AccessRequestRecord, ChangeRecord
from ..db.models.mcp_models import MCPToolCall
from ..db.models.terminal import TerminalApproval
from ..db.models.workflows import WorkflowDefinition, WorkflowRun
from .artifact_service import ArtifactApproval

SOURCES = ("agent", "workflow", "mcp", "entity_action", "access", "change")

_RISK_RANK = {"low": 0, "medium": 1, "high": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: Optional[datetime]) -> datetime:
    if dt is None:
        return _now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _age_seconds(created_at: Optional[datetime]) -> int:
    return max(0, int((_now() - _aware(created_at)).total_seconds()))


def _loads(raw: Optional[str], default: Any) -> Any:
    try:
        data = json.loads(raw or "")
        return data if data is not None else default
    except (TypeError, ValueError):
        return default


def _normalize_risk(raw: str | None) -> str:
    r = (raw or "").strip().lower()
    if r in {"moderate", "medium"}:
        return "medium"
    if r in {"high", "critical"}:
        return "high"
    if r in {"low"}:
        return "low"
    return "medium"


def _item(
    *,
    id: str,
    source: str,
    title: str,
    description: str,
    risk: str,
    grounding: str | None,
    requester: str,
    created_at: Optional[datetime],
    needs_typed_confirmation: bool = False,
    needs_second_approver: bool = False,
    approvers: Optional[list[str]] = None,
    approvals_required: Optional[int] = None,
    service: Optional[str] = None,
    workspace_id: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    sla_minutes: int = 30,
) -> dict[str, Any]:
    age_s = _age_seconds(created_at)
    return {
        "id": id,
        "source": source,
        "title": title,
        "description": description,
        "risk": _normalize_risk(risk),
        "grounding": grounding,
        "requester": requester or "unknown",
        "created_at": _aware(created_at).isoformat(),
        "age_seconds": age_s,
        "sla_breached": age_s > sla_minutes * 60,
        "needs_typed_confirmation": bool(needs_typed_confirmation),
        "needs_second_approver": bool(needs_second_approver),
        "approvers": approvers or [],
        "approvals_required": approvals_required,
        "service": service,
        "workspace_id": workspace_id,
        "detail": detail or {},
    }


# ── per-source normalization ────────────────────────────────────────────────


def _normalize_agent_run(session: Session, row: AgentRun, *, sla_minutes: int) -> dict[str, Any]:
    details = _loads(row.details_json, {})
    src = str(details.get("source") or "")
    title = f"Agent run: {row.agent}"
    description = row.summary or ""
    detail: dict[str, Any] = {"task": row.task, "agent": row.agent}
    typed = False
    dual = False
    approvers: list[str] = []
    approvals_required: Optional[int] = None
    risk = "high" if (row.environment or "") == "production" else "medium"

    if src == "artifact" or details.get("artifact_approval_id"):
        approval_id = details.get("artifact_approval_id")
        art = session.get(ArtifactApproval, approval_id) if approval_id else None
        if art:
            preview = _loads(art.preview_json, {})
            params = _loads(art.params_json, {})
            title = f"{art.connector}.{art.method}"
            description = row.summary or f"Write-back proposal: {art.connector}.{art.method}"
            detail = {"connector": art.connector, "method": art.method, "params": params, "preview": preview}
            destroy_count = int(preview.get("destroy_count") or params.get("destroy_count") or 0)
            typed = bool(preview.get("require_typed_confirm")) or destroy_count > 0
            approvals_required = int(art.approvals_required or 1)
            dual = approvals_required > 1
            approvers = _loads(art.approvers_json, [])
            risk = "high" if (typed or dual) else risk
    elif row.agent == "catalog_self_service" or details.get("catalog_action_id"):
        title = f"Catalog action: {details.get('action_type') or 'action'} on {details.get('entity_name') or details.get('entity_id') or ''}".strip()
        description = row.summary or "Catalog self-service action awaiting approval"
        detail = {
            "action_type": details.get("action_type"),
            "entity_name": details.get("entity_name"),
            "payload": details.get("payload"),
        }
        risk = _normalize_risk(details.get("risk"))
    elif row.agent == "terminal" or src == "terminal":
        title = "Terminal command"
        approval_id = details.get("terminal_approval_id")
        term = session.get(TerminalApproval, approval_id) if approval_id else None
        if term:
            description = term.command
            detail = {"command": term.command, "reasons": _loads(term.reasons_json, [])}
        else:
            description = row.summary or ""
    elif row.agent == "editor_pr" or src == "editor":
        title = "Editor PR proposal"
        description = row.summary or ""
        detail = {"editor_approval_id": details.get("editor_approval_id")}
    else:
        payload = _loads(row.approval_payload_json, {})
        commands = payload.get("commands") or []
        detail = {"commands": commands, "task": row.task}

    return _item(
        id=f"agent:{row.id}",
        source="agent",
        title=title,
        description=description,
        risk=risk,
        grounding=None,
        requester=row.triggered_by,
        created_at=row.created_at,
        needs_typed_confirmation=typed,
        needs_second_approver=dual,
        approvers=approvers,
        approvals_required=approvals_required,
        service=None,
        workspace_id=row.workspace_id,
        detail=detail,
        sla_minutes=sla_minutes,
    )


def _normalize_workflow_run(
    session: Session, row: WorkflowRun, *, sla_minutes: int, wf_cache: dict[str, WorkflowDefinition]
) -> dict[str, Any]:
    wf = wf_cache.get(row.workflow_id)
    if wf is None:
        wf = session.get(WorkflowDefinition, row.workflow_id)
        if wf is not None:
            wf_cache[row.workflow_id] = wf
    steps_state = _loads(row.steps_state_json, {})
    gate = steps_state.get(row.current_step_id or "") or {}
    prompt = gate.get("prompt") or f"Approve workflow step '{row.current_step_id}'?"
    return _item(
        id=f"workflow:{row.id}",
        source="workflow",
        title=f"Workflow: {wf.name if wf else row.workflow_id}",
        description=prompt,
        risk=wf.risk if wf else "medium",
        grounding=row.grounding,
        requester=row.triggered_by,
        created_at=row.started_at,
        service=None,
        workspace_id=wf.workspace_id if wf else None,
        detail={
            "workflow_name": wf.name if wf else None,
            "step_id": row.current_step_id,
            "prompt": prompt,
            "dry_run": bool(row.dry_run),
        },
        sla_minutes=sla_minutes,
    )


def _normalize_mcp_call(row: MCPToolCall, *, sla_minutes: int) -> dict[str, Any]:
    return _item(
        id=f"mcp:{row.id}",
        source="mcp",
        title=f"MCP tool: {row.server_name}.{row.tool_name}",
        description=f"Dangerous MCP tool call on server '{row.server_name}'"
        if row.dangerous
        else f"MCP tool call requiring approval on server '{row.server_name}'",
        risk="high" if row.dangerous else "medium",
        grounding=None,
        requester=row.requested_by,
        created_at=row.created_at,
        service=row.server_name,
        detail={
            "server_name": row.server_name,
            "tool_name": row.tool_name,
            "arguments": _loads(row.arguments_json, {}),
            "dangerous": bool(row.dangerous),
        },
        sla_minutes=sla_minutes,
    )


def _normalize_entity_action_run(row: Any, entity: Any, action_name: str, *, sla_minutes: int) -> dict[str, Any]:
    inputs = _loads(row.inputs_json, {})
    return _item(
        id=f"entity_action:{row.id}",
        source="entity_action",
        title=f"Entity action: {action_name} on {entity.name}",
        description=f"Self-service action '{action_name}' on {entity.kind} '{entity.name}'",
        risk="medium",
        grounding=None,
        requester=row.requested_by,
        created_at=row.created_at,
        service=entity.name,
        detail={"action_name": action_name, "entity_name": entity.name, "entity_kind": entity.kind, "inputs": inputs},
        sla_minutes=sla_minutes,
    )


def _normalize_access_request(row: AccessRequestRecord, *, sla_minutes: int) -> dict[str, Any]:
    policy = _loads(row.policy_assessment_json, {})
    return _item(
        id=f"access:{row.id}",
        source="access",
        title=f"Access: {row.subject_username} → {row.resource_name or row.resource_id}",
        description=row.justification or f"{row.resource_type} grant requested by {row.requester_username}",
        risk=policy.get("risk") or "low",
        grounding=None,
        requester=row.requester_username,
        created_at=row.created_at,
        service=row.resource_name or row.resource_id,
        workspace_id=row.workspace_id,
        detail={
            "resource_type": row.resource_type,
            "resource_id": row.resource_id,
            "resource_name": row.resource_name,
            "subject_username": row.subject_username,
            "owner_username": row.owner_username,
            "owner_missing": bool(row.owner_missing),
            "duration_hours": row.duration_hours,
            "policy_assessment": policy,
        },
        sla_minutes=sla_minutes,
    )


def _normalize_change_record(row: ChangeRecord, *, sla_minutes: int) -> dict[str, Any]:
    blast = _loads(row.blast_radius_json, {})
    return _item(
        id=f"change:{row.id}",
        source="change",
        title=f"Change: {row.title or row.change_type}",
        description=row.description or "",
        risk=row.risk,
        grounding=None,
        requester="system",
        created_at=row.created_at,
        service=blast.get("root_entity_name"),
        workspace_id=row.workspace_id,
        detail={
            "change_type": row.change_type,
            "blast_radius": blast,
            "rollback_plan": row.rollback_plan,
            "external_id": row.external_id,
            "external_url": row.external_url,
            "status": row.status,
        },
        sla_minutes=sla_minutes,
    )


# ── fetch all pending items for a tenant ────────────────────────────────────


def _fetch_all(session: Session, tenant_id: str, *, sla_minutes: int) -> list[dict[str, Any]]:
    from ..routers.catalog import CatalogEntity
    from ..routers.entity_actions import EntityAction, EntityActionRun

    items: list[dict[str, Any]] = []

    agent_rows = session.exec(
        select(AgentRun).where(AgentRun.status == "pending_approval", AgentRun.tenant_id == tenant_id)
    ).all()
    for row in agent_rows:
        items.append(_normalize_agent_run(session, row, sla_minutes=sla_minutes))

    wf_cache: dict[str, WorkflowDefinition] = {}
    workflow_rows = session.exec(
        select(WorkflowRun).where(WorkflowRun.status == "pending_approval", WorkflowRun.tenant_id == tenant_id)
    ).all()
    for row in workflow_rows:
        items.append(_normalize_workflow_run(session, row, sla_minutes=sla_minutes, wf_cache=wf_cache))

    mcp_rows = session.exec(
        select(MCPToolCall).where(MCPToolCall.status == "pending_approval", MCPToolCall.tenant_id == tenant_id)
    ).all()
    for row in mcp_rows:
        items.append(_normalize_mcp_call(row, sla_minutes=sla_minutes))

    # EntityActionRun has no tenant_id column — scope via CatalogEntity.tenant_id.
    entity_rows = session.exec(select(EntityActionRun).where(EntityActionRun.status == "pending")).all()
    if entity_rows:
        entity_ids = {r.entity_id for r in entity_rows}
        entities = {
            e.id: e
            for e in session.exec(
                select(CatalogEntity).where(
                    col(CatalogEntity.id).in_(entity_ids), CatalogEntity.tenant_id == tenant_id
                )
            ).all()
        }
        action_ids = {r.action_id for r in entity_rows}
        actions = {
            a.id: a for a in session.exec(select(EntityAction).where(col(EntityAction.id).in_(action_ids))).all()
        }
        for row in entity_rows:
            entity = entities.get(row.entity_id)
            if entity is None:
                continue  # not in this tenant
            action = actions.get(row.action_id)
            items.append(
                _normalize_entity_action_run(
                    row, entity, action.name if action else "action", sla_minutes=sla_minutes
                )
            )

    access_rows = session.exec(
        select(AccessRequestRecord).where(
            AccessRequestRecord.status == "pending_approval", AccessRequestRecord.tenant_id == tenant_id
        )
    ).all()
    for row in access_rows:
        items.append(_normalize_access_request(row, sla_minutes=sla_minutes))

    change_rows = session.exec(
        select(ChangeRecord).where(
            col(ChangeRecord.status).in_(["draft", "submitted"]), ChangeRecord.tenant_id == tenant_id
        )
    ).all()
    for row in change_rows:
        items.append(_normalize_change_record(row, sla_minutes=sla_minutes))

    return items


def list_inbox_items(
    tenant_id: str,
    *,
    risk: Optional[str] = None,
    source: Optional[str] = None,
    service: Optional[str] = None,
    min_age_seconds: Optional[int] = None,
    sort: str = "age",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 25,
    sla_minutes: int = 30,
) -> dict[str, Any]:
    with Session(engine) as session:
        items = _fetch_all(session, tenant_id, sla_minutes=sla_minutes)

    if risk:
        items = [i for i in items if i["risk"] == risk]
    if source:
        items = [i for i in items if i["source"] == source]
    if service:
        needle = service.strip().lower()
        items = [i for i in items if needle in (i.get("service") or "").lower()]
    if min_age_seconds is not None:
        items = [i for i in items if i["age_seconds"] >= min_age_seconds]

    reverse = sort_dir != "asc"
    if sort == "risk":
        items.sort(key=lambda i: _RISK_RANK.get(i["risk"], 1), reverse=reverse)
    else:
        items.sort(key=lambda i: i["age_seconds"], reverse=reverse)

    total = len(items)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return {"items": page_items, "total": total, "page": page, "page_size": page_size}


def get_inbox_item(item_id: str, tenant_id: str, *, sla_minutes: int = 30) -> dict[str, Any]:
    with Session(engine) as session:
        items = _fetch_all(session, tenant_id, sla_minutes=sla_minutes)
    for item in items:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Approval item not found")


def _split(item_id: str) -> tuple[str, str]:
    if ":" not in item_id:
        raise HTTPException(status_code=400, detail="Invalid approval item id")
    source, native_id = item_id.split(":", 1)
    if source not in SOURCES:
        raise HTTPException(status_code=400, detail=f"Unknown approval source '{source}'")
    return source, native_id


async def approve_item(
    item_id: str, tenant_id: str, user: User, *, confirmation: Optional[str] = None
) -> dict[str, Any]:
    source, native_id = _split(item_id)

    if source == "agent":
        from .agent_run_approvals import approve_agent_run

        return await approve_agent_run(native_id, tenant_id, user, confirmation)

    if source == "workflow":
        return await _serialize_workflow_run(native_id, tenant_id, user)

    if source == "mcp":
        from ..mcp.hitl_bridge import approve_call

        return await approve_call(call_id=native_id, user=user, tenant_id=tenant_id)

    if source == "entity_action":
        from ..routers.entity_actions import approve_entity_action_run_core

        return await approve_entity_action_run_core(native_id, tenant_id, user)

    if source == "access":
        from .access_service import provision_access_request

        return await provision_access_request(request_id=native_id, tenant_id=tenant_id, approver=user.username, user=user)

    if source == "change":
        from .change_service import mark_change_approved

        return mark_change_approved(change_id=native_id, tenant_id=tenant_id, actor=user.username)

    raise HTTPException(status_code=400, detail=f"Unknown approval source '{source}'")


async def _serialize_workflow_run(run_id: str, tenant_id: str, user: User) -> dict[str, Any]:
    from .workflow_engine import resume_after_approval, serialize_run

    run = await resume_after_approval(run_id, "", user.username, tenant_id)
    return serialize_run(run)


async def reject_item(item_id: str, tenant_id: str, user: User, *, reason: Optional[str] = None) -> dict[str, Any]:
    source, native_id = _split(item_id)

    if source == "agent":
        from .agent_run_approvals import reject_agent_run

        return reject_agent_run(native_id, tenant_id, user)

    if source == "workflow":
        from .workflow_engine import reject_workflow, serialize_run

        run = await reject_workflow(native_id, "", user.username, reason or "Rejected", tenant_id)
        return serialize_run(run)

    if source == "mcp":
        from ..mcp.hitl_bridge import reject_call

        return reject_call(call_id=native_id, user=user, tenant_id=tenant_id, reason=reason or "")

    if source == "entity_action":
        from ..routers.entity_actions import reject_entity_action_run_core

        return reject_entity_action_run_core(native_id, tenant_id, user)

    if source == "access":
        from .access_service import reject_access_request

        return reject_access_request(request_id=native_id, tenant_id=tenant_id, decided_by=user.username, reason=reason or "")

    if source == "change":
        from .change_service import reject_change_record

        return reject_change_record(change_id=native_id, tenant_id=tenant_id, actor=user.username, reason=reason or "")

    raise HTTPException(status_code=400, detail=f"Unknown approval source '{source}'")


async def bulk_approve(item_ids: list[str], tenant_id: str, user: User) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for item_id in item_ids:
        try:
            item = get_inbox_item(item_id, tenant_id)
        except HTTPException as exc:
            results.append({"id": item_id, "ok": False, "error": str(exc.detail)})
            continue
        if item["risk"] != "low" or item["needs_typed_confirmation"] or item["needs_second_approver"]:
            results.append(
                {
                    "id": item_id,
                    "ok": False,
                    "error": "Requires individual review (risk is not low, or needs typed/second-approver confirmation)",
                }
            )
            continue
        try:
            out = await approve_item(item_id, tenant_id, user)
            results.append({"id": item_id, "ok": True, "result": out})
        except HTTPException as exc:
            results.append({"id": item_id, "ok": False, "error": str(exc.detail)})
    return {"results": results}
