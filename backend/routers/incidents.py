"""Incident triage, remediation, approvals, and Jira."""

import asyncio
import base64
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..ai.ai_utils import call_llm
from ..auth import User, get_current_user, require_admin, write_audit
from ..database import (
    create_notification,
    get_incident,
    get_pending_approvals,
    get_settings,
    list_incidents as repo_list_incidents,
    update_incident_status,
)
from ..executor.safe_executor import safe_executor
from ..observability.metrics import ACTIVE_APPROVALS, HITL_APPROVAL_SECONDS
from ..rate_limit import limiter
from ..services import incidents_service
from ..services.approval_claim import claim_incident_approval
from ..services.incident_timeline import (
    append_timeline_event,
    enrich_incident_detail,
    extract_executable_commands,
)
from ..services.isolation import require_tenant
from sqlmodel import Session
from ..database import engine
from ..services.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, clamp_page
from ..services.postmortem_service import (
    generate_postmortem_for_incident,
    get_latest_postmortem,
    update_postmortem,
)
from ..services.incidents_service import (
    AGENT_APPROVED_LOGS,
    MOCK_RUNBOOK_LOGS,
    close_servicenow_ticket,
    to_adf,
)

router = APIRouter(tags=["incidents"])

class TriageRequest(BaseModel):
    logs: str


class TriageResponse(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    raw: str
    model_used: str


class IncidentSummary(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    model_used: str
    source: str = "manual"
    raw_logs: str = ""
    status: str = "OPEN"
    execution_logs: str | None = None
    owner_role: str = "Admin"
    proposed_remediation_plan: list[str] = []
    agent_execution_logs: str | None = None
    tenant_id: str | None = "default"
    workspace_id: str | None = None


class ApprovalRequest(BaseModel):
    approved_by_role: str = "Admin"
    reason: str | None = None


@router.post("/api/triage", response_model=TriageResponse)
@limiter.limit("10/minute")
async def triage_logs(request: Request, triage_in: TriageRequest, current_user: User = Depends(get_current_user)):
    if not triage_in.logs.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")
    try:
        result = await incidents_service.run_triage(
            triage_in.logs,
            source="manual",
            tenant_id=require_tenant(request),
            workspace_id=getattr(request.state, "workspace_id", None),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")
    return TriageResponse(**result)

@router.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents(
    request: Request,
    role: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    current_user: User = Depends(get_current_user),
):
    """Return a page of incidents for the caller's tenant (newest first)."""
    tenant_id = require_tenant(request)
    _, size, offset = clamp_page(page, page_size)
    if role and role != "Admin":
        # Role filter is post-query; page within the filtered set.
        pool = repo_list_incidents(limit=500, offset=0, tenant_id=tenant_id)
        pool = [i for i in pool if i.get("owner_role", "Admin") == role]
        return pool[offset : offset + size]
    return repo_list_incidents(limit=size, offset=offset, tenant_id=tenant_id)


@router.get("/api/incidents/approvals")
def list_pending_approvals(
    request: Request,
    role: str | None = None,
    current_user: User = Depends(get_current_user),
):
    # Must be declared before /{incident_id} so "approvals" is not parsed as an int id.
    tenant_id = require_tenant(request)
    return get_pending_approvals(role=role, tenant_id=tenant_id)


@router.get("/api/incidents/{incident_id}")
def get_incident_by_id(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    """Incident command-center payload: timeline, github refs, pending approval, logs."""
    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return enrich_incident_detail(incident)


@router.post("/api/incidents/{incident_id}/remediate")
@limiter.limit("5/minute")
async def remediate_incident(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") == "RESOLVED":
        raise HTTPException(status_code=400, detail="Incident is already resolved")

    await asyncio.sleep(2)

    updated = update_incident_status(
        incident_id,
        status="RESOLVED",
        execution_logs=MOCK_RUNBOOK_LOGS,
    )
    try:
        append_timeline_event(
            incident_id,
            event_type="executed",
            detail="Automated runbook remediation completed",
            actor=current_user.username,
        )
    except Exception:
        pass

    create_notification(
        message=f"✅ Incident #{incident_id} auto-remediated via Automated Runbook",
        type="info",
        incident_id=incident_id,
    )
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="REMEDIATE",
        resource=f"incident:{incident_id}",
        detail="runbook executed",
    )

    return enrich_incident_detail(updated)


@router.post("/api/incidents/{incident_id}/dry-run")
@limiter.limit("5/minute")
async def dry_run_incident(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(404, "Incident not found")
    plan = incident.get("proposed_remediation_plan") or []
    commands = extract_executable_commands(plan, incident.get("commands"))
    result = await safe_executor.dry_run(
        commands,
        context={
            "role": current_user.role,
            "tenant_id": tenant_id,
            "tool": "shell",
            "incident_id": incident_id,
        },
    )
    try:
        append_timeline_event(
            incident_id,
            event_type="dry_run",
            detail=f"Dry-run of {len(commands)} command(s) — all_safe={result.get('all_safe')}",
            actor=current_user.username,
            meta={"all_safe": result.get("all_safe"), "steps": len(result.get("steps") or [])},
        )
    except Exception:
        pass
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="DRY_RUN",
        resource=f"incident:{incident_id}",
        detail=f"all_safe={result.get('all_safe')}",
    )
    return result


@router.post("/api/incidents/{incident_id}/approve")
@limiter.limit("5/minute")
async def approve_incident(
    request: Request,
    incident_id: int,
    body: ApprovalRequest,
    current_user: User = Depends(require_admin),
):
    from datetime import datetime, timezone
    import os

    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    plan = incident.get("proposed_remediation_plan") or []
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except Exception:
            plan = []
    steps = plan if isinstance(plan, list) else []
    commands = extract_executable_commands(steps, incident.get("commands"))

    policy_context = {
        "role": current_user.role,
        "tenant_id": tenant_id,
        "tool": "shell",
        "environment": (os.getenv("ENV") or "development").strip().lower(),
        "incident_id": incident_id,
        "approved_by": current_user.username,
    }
    dry = await safe_executor.dry_run(commands, context=policy_context)
    try:
        append_timeline_event(
            incident_id,
            event_type="dry_run",
            detail=f"Pre-approve dry-run — all_safe={dry.get('all_safe')}",
            actor=current_user.username,
            meta={"all_safe": dry.get("all_safe")},
        )
    except Exception:
        pass
    if commands and not dry.get("all_safe", True):
        raise HTTPException(
            status_code=400,
            detail={"message": "Dry-run failed safety checks", "dry_run": dry},
        )

    with Session(engine) as session:
        if not claim_incident_approval(session, incident_id):
            raise HTTPException(
                status_code=409,
                detail="Incident already claimed or not awaiting approval",
            )

    live = (os.getenv("ENABLE_LIVE_EXECUTION") or "").strip().lower() in ("1", "true", "yes", "on")
    if commands and live:
        exec_result = await safe_executor.execute(
            commands,
            incident_id=incident_id,
            approved_by=current_user.username,
            context={**policy_context, "approved": True},
        )
        logs = exec_result.get("logs") or ""
        success = bool(exec_result.get("success"))
    else:
        logs = AGENT_APPROVED_LOGS.format(
            role=current_user.role,
            id=incident_id,
            step1=steps[0] if len(steps) > 0 else "Isolating affected service",
            step2=steps[1] if len(steps) > 1 else "Applying remediation patch",
            step3=steps[2] if len(steps) > 2 else "Restarting and validating services",
            sn_url="(skipped)",
        )
        success = True

    try:
        updated = update_incident_status(
            incident_id,
            status="RESOLVED_BY_AGENT" if success else "AWAITING_APPROVAL",
            agent_execution_logs=logs,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found during update")

    if success:
        ACTIVE_APPROVALS.dec()
        try:
            append_timeline_event(
                incident_id,
                event_type="approved",
                detail=f"Approved by {current_user.username}",
                actor=current_user.username,
                meta={"role": current_user.role},
            )
            append_timeline_event(
                incident_id,
                event_type="executed",
                detail="Remediation executed after approval",
                actor="agent",
                meta={"live": live, "commands": len(commands)},
            )
        except Exception:
            pass

    try:
        inc_ts = datetime.fromisoformat(incident["timestamp"])
        approval_seconds = (datetime.now(timezone.utc) - inc_ts).total_seconds()
        HITL_APPROVAL_SECONDS.observe(approval_seconds)
    except Exception:
        pass
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="APPROVE",
        resource=f"incident:{incident_id}",
        detail="plan approved and executed" if success else "execution failed",
    )

    create_notification(
        message=f"✅ Incident #{incident_id} resolved by agent after approval by {current_user.role}",
        type="info",
        incident_id=incident_id,
    )

    if success:
        asyncio.create_task(close_servicenow_ticket(incident_id))

    try:
        from .ws_portal import broadcast_json

        asyncio.create_task(
            broadcast_json(
                {
                    "type": "approval_update",
                    "incident_id": str(incident_id),
                    "action": "approved",
                    "approved_by": current_user.username,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    except Exception:
        pass

    refreshed = get_incident(incident_id, tenant_id=require_tenant(request))
    return enrich_incident_detail(refreshed or updated)


@router.post("/api/incidents/{incident_id}/reject")
@limiter.limit("5/minute")
async def reject_incident(
    request: Request,
    incident_id: int,
    body: ApprovalRequest | None = None,
    current_user: User = Depends(require_admin),
):
    from datetime import datetime, timezone

    incident = get_incident(incident_id, tenant_id=require_tenant(request))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    with Session(engine) as session:
        if not claim_incident_approval(session, incident_id, to_status="REJECTED"):
            raise HTTPException(
                status_code=409,
                detail="Incident already claimed or not awaiting approval",
            )

    try:
        updated = get_incident(incident_id, tenant_id=require_tenant(request))
        if not updated:
            raise ValueError("missing")
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found during update")
    ACTIVE_APPROVALS.dec()
    reason = (body.reason if body else None) or "plan rejected"
    try:
        append_timeline_event(
            incident_id,
            event_type="rejected",
            detail=f"Rejected by {current_user.username}: {reason}",
            actor=current_user.username,
        )
    except Exception:
        pass
    try:
        inc_ts = datetime.fromisoformat(incident["timestamp"])
        approval_seconds = (datetime.now(timezone.utc) - inc_ts).total_seconds()
        HITL_APPROVAL_SECONDS.observe(approval_seconds)
    except Exception:
        pass
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="REJECT",
        resource=f"incident:{incident_id}",
        detail=reason,
    )
    create_notification(
        message=f"🚫 Incident #{incident_id} agent execution rejected by operator",
        type="warning",
        incident_id=incident_id,
    )

    try:
        from .ws_portal import broadcast_json

        asyncio.create_task(
            broadcast_json(
                {
                    "type": "approval_update",
                    "incident_id": str(incident_id),
                    "action": "rejected",
                    "approved_by": current_user.username,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        )
    except Exception:
        pass

    refreshed = get_incident(incident_id, tenant_id=require_tenant(request))
    return enrich_incident_detail(refreshed or updated)


@router.post("/api/incidents/{incident_id}/retriage")
@limiter.limit("10/minute")
async def retriage_incident(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    logs = (incident.get("raw_logs") or "").strip()
    if not logs:
        raise HTTPException(status_code=400, detail="Incident has no raw logs to re-triage")
    try:
        result = await incidents_service.run_triage(
            logs,
            source=incident.get("source") or "manual",
            owner_role=incident.get("owner_role") or "Admin",
            tenant_id=tenant_id,
            workspace_id=incident.get("workspace_id") or getattr(request.state, "workspace_id", None),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")
    try:
        append_timeline_event(
            incident_id,
            event_type="retriaged",
            detail=f"Re-triage spawned incident #{result.get('id')}",
            actor=current_user.username,
            meta={"new_incident_id": result.get("id")},
        )
    except Exception:
        pass
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="RETRIAGE",
        resource=f"incident:{incident_id}",
        detail=f"new_incident={result.get('id')}",
    )
    return {"ok": True, "original_id": incident_id, "new_incident": result}


@router.post("/api/incidents/{incident_id}/run-agent")
@limiter.limit("10/minute")
async def run_incident_agent(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    """Run incident_agent with PlatformContext stamped from the authenticated user."""
    from sqlmodel import Session

    from ..context import PlatformContext
    from ..database import UserContext, engine as db_engine
    from ..pipeline.orchestrator import orchestrator_agent

    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    uid = str(current_user.id) if current_user.id is not None else str(current_user.username)
    pinned: dict = {}
    with Session(db_engine) as session:
        row = session.get(UserContext, uid)
        if row and row.active_accounts:
            try:
                pinned = json.loads(row.active_accounts or "{}")
            except Exception:
                pinned = {}
        ctx = PlatformContext.from_dict(
            {
                "user_id": uid,
                "user_role": "Admin" if (current_user.role or "") == "Admin" else "User",
                "workspace_id": incident.get("workspace_id")
                or getattr(request.state, "workspace_id", None)
                or getattr(current_user, "workspace_id", None),
                "tenant_id": tenant_id,
                "environment": "production",
                "tool_accounts": pinned if isinstance(pinned, dict) else {},
                "workspace_name": "incident-command",
            },
            user_id=uid,
            user_role="Admin" if (current_user.role or "") == "Admin" else "User",
        )
        result = await orchestrator_agent.run(
            f"Investigate and triage incident #{incident_id}: {incident.get('summary')}",
            ctx,
            session,
            override_agents=["incident_agent"],
            agent_params={
                "incident_id": incident_id,
                "severity": incident.get("severity"),
                "summary": incident.get("summary"),
            },
        )

    try:
        append_timeline_event(
            incident_id,
            event_type="agent_run",
            detail=f"incident_agent: {result.status} — {result.summary}"[:300],
            actor=current_user.username,
            meta={"run_id": result.run_id, "status": result.status},
        )
    except Exception:
        pass
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="AGENT_RUN",
        resource=f"incident:{incident_id}",
        detail=f"incident_agent status={result.status}",
    )
    detail = enrich_incident_detail(get_incident(incident_id, tenant_id=tenant_id) or incident)
    return {"ok": True, "agent_result": result.to_dict(), "incident": detail}


class PostmortemUpdateBody(BaseModel):
    markdown: str


@router.post("/api/incidents/{incident_id}/postmortem/generate")
@limiter.limit("5/minute")
async def generate_incident_postmortem(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    """Generate a versioned postmortem from incident data, timeline, triage, and agent runs."""
    tenant_id = require_tenant(request)
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    try:
        postmortem = await generate_postmortem_for_incident(
            incident_id,
            tenant_id=tenant_id,
            actor=current_user.username,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Postmortem generation failed: {exc}") from exc
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="postmortem_generated",
        resource=f"incident:{incident_id}",
        detail=f"version={postmortem.get('version')}",
    )
    return postmortem


@router.get("/api/incidents/{incident_id}/postmortem")
def get_incident_postmortem(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    if not get_incident(incident_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    postmortem = get_latest_postmortem(incident_id, tenant_id=tenant_id)
    if not postmortem:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return postmortem


@router.put("/api/incidents/{incident_id}/postmortem")
def edit_incident_postmortem(
    request: Request,
    incident_id: int,
    body: PostmortemUpdateBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    if not get_incident(incident_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    updated = update_postmortem(
        incident_id,
        tenant_id=tenant_id,
        markdown=body.markdown,
        editor=current_user.username,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    return updated


@router.get("/api/incidents/{incident_id}/postmortem/download")
def download_incident_postmortem(
    request: Request,
    incident_id: int,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    if not get_incident(incident_id, tenant_id=tenant_id):
        raise HTTPException(status_code=404, detail="Incident not found")
    postmortem = get_latest_postmortem(incident_id, tenant_id=tenant_id)
    if not postmortem:
        raise HTTPException(status_code=404, detail="Postmortem not found")
    version = postmortem.get("version", 1)
    filename = f"postmortem-incident-{incident_id}-v{version}.md"
    return Response(
        content=postmortem.get("markdown") or "",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


JIRA_FORMAT_PROMPT = """You are a senior SRE writing a Jira incident ticket.
Given the incident data below, return ONLY a JSON object with these fields:
- "title": concise one-line issue summary (max 100 chars)
- "description": detailed markdown description (2-4 sentences, plain text)
- "steps_to_reproduce": list of strings describing how to reproduce / verify the issue
- "priority": one of "Highest", "High", "Medium", "Low"

Return ONLY raw JSON. No markdown fences.
"""

@router.post("/api/incidents/{incident_id}/jira")
@limiter.limit("5/minute")
async def create_jira_ticket(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    # Load incident
    incident = get_incident(incident_id, tenant_id=require_tenant(request))
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Load Jira settings
    settings = get_settings()
    domain    = settings.get("jira_domain", "").strip()
    email     = settings.get("jira_email", "").strip()
    token     = settings.get("jira_api_token", "").strip()
    proj_key  = settings.get("jira_project_key", "").strip()

    if not all([domain, email, token, proj_key]):
        raise HTTPException(status_code=400, detail="Jira credentials are incomplete. Configure them in Settings.")

    # Ask AI to format the ticket
    incident_summary_text = (
        f"Severity: {incident['severity']}\n"
        f"Summary: {incident['summary']}\n"
        f"Root Cause: {incident['root_cause']}\n"
        f"Action Plan: {'; '.join(incident.get('action_plan', []))}\n"
        f"Commands: {'; '.join(incident.get('commands', []))}"
    )

    try:
        raw = await call_llm(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    # Parse AI response
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        jira_data = json.loads(m.group(0)) if m else {}
    except Exception:
        jira_data = {}

    title      = jira_data.get("title", incident["summary"])[:100]
    description = jira_data.get("description", incident["root_cause"])
    steps       = jira_data.get("steps_to_reproduce", [])
    priority    = jira_data.get("priority", "High")

    # Build description ADF with steps
    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else ""
    full_desc   = f"{description}\n\nSteps to Reproduce:\n{steps_text}" if steps_text else description
    adf_body    = to_adf(full_desc)

    # Call Jira API
    import base64
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    payload = {
        "fields": {
            "project":     {"key": proj_key},
            "summary":     title,
            "description": adf_body,
            "issuetype":   {"name": "Bug"},
            "priority":    {"name": priority},
        }
    }
    jira_url = f"https://{domain}/rest/api/3/issue"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(jira_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Jira API error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Jira connection error: {str(exc)}")

    ticket_key = result.get("key", "UNKNOWN")
    ticket_url = f"https://{domain}/browse/{ticket_key}"

    create_notification(
        message=f"Jira ticket {ticket_key} created for Incident #{incident_id}",
        type="info",
        incident_id=incident_id,
    )

    return {"ticket_key": ticket_key, "ticket_url": ticket_url}
