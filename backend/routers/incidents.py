"""Incident triage, remediation, approvals, and Jira."""

import asyncio
import base64
import json
import os
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..ai.ai_utils import call_gemini, call_ollama
from ..auth import User, get_current_user, write_audit
from ..database import (
    create_notification,
    get_all_incidents,
    get_pending_approvals,
    get_settings,
    update_incident_status,
)
from ..executor.safe_executor import safe_executor
from ..observability.metrics import ACTIVE_APPROVALS, HITL_APPROVAL_SECONDS
from ..rate_limit import limiter
from ..services import incidents_service
from ..services.incidents_service import (
    AGENT_APPROVED_LOGS,
    MOCK_RUNBOOK_LOGS,
    _SERVICENOW_MOCK_URL,
    close_servicenow_ticket,
    to_adf,
)

router = APIRouter(tags=["incidents"])

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()

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


class ApprovalRequest(BaseModel):
    approved_by_role: str = "Admin"


@router.post("/api/triage", response_model=TriageResponse)
@limiter.limit("5/minute")
async def triage_logs(request: Request, triage_in: TriageRequest, current_user: User = Depends(get_current_user)):
    if not triage_in.logs.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")
    try:
        result = await incidents_service.run_triage(triage_in.logs, source="manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")
    return TriageResponse(**result)

@router.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents(role: str | None = None, current_user: User = Depends(get_current_user)):
    """Return all incidents. If ?role=<X> is provided and role != Admin,
    only incidents where owner_role matches are returned."""
    incidents = get_all_incidents()
    if role and role != "Admin":
        incidents = [i for i in incidents if i.get("owner_role", "Admin") == role]
    return incidents

@router.post("/api/incidents/{incident_id}/remediate")
@limiter.limit("5/minute")
async def remediate_incident(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") == "RESOLVED":
        raise HTTPException(status_code=400, detail="Incident is already resolved")

    # Simulate execution delay
    await asyncio.sleep(2)

    updated = update_incident_status(
        incident_id,
        status="RESOLVED",
        execution_logs=MOCK_RUNBOOK_LOGS,
    )

    create_notification(
        message=f"✅ Incident #{incident_id} auto-remediated via Automated Runbook",
        type="info",
        incident_id=incident_id,
    )

    return updated

class ApprovalRequest(BaseModel):
    approved_by_role: str = "Admin"


@router.post("/api/incidents/{incident_id}/dry-run")
@limiter.limit("5/minute")
async def dry_run_incident(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(404, "Incident not found")
    plan = incident.get("proposed_remediation_plan") or []
    commands = [s for s in (plan if isinstance(plan, list) else []) if s.startswith("Run:") or "kubectl" in s or "docker" in s or "git" in s]
    return await safe_executor.dry_run(commands)

@router.post("/api/incidents/{incident_id}/approve")
@limiter.limit("5/minute")
async def approve_incident(request: Request, incident_id: int, body: ApprovalRequest, current_user: User = Depends(get_current_user)):
    import json as _json
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    plan = incident.get("proposed_remediation_plan") or []
    if isinstance(plan, str):
        try:
            plan = _json.loads(plan)
        except Exception:
            plan = []
    steps = plan if isinstance(plan, list) else []

    await asyncio.sleep(3)   # simulate execution

    logs = AGENT_APPROVED_LOGS.format(
        role=current_user.role,
        id=incident_id,
        step1=steps[0] if len(steps) > 0 else "Isolating affected service",
        step2=steps[1] if len(steps) > 1 else "Applying remediation patch",
        step3=steps[2] if len(steps) > 2 else "Restarting and validating services",
        sn_url=_SERVICENOW_MOCK_URL,
    )

    try:
        updated = update_incident_status(
            incident_id,
            status="RESOLVED_BY_AGENT",
            agent_execution_logs=logs,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found during update")
    ACTIVE_APPROVALS.dec()
    try:
        from datetime import datetime, timezone

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
        detail="plan approved"
    )

    create_notification(
        message=f"✅ Incident #{incident_id} resolved by agent after approval by {current_user.role}",
        type="info",
        incident_id=incident_id,
    )

    # Fire mock ServiceNow ticket-close webhook (fire-and-forget)
    asyncio.create_task(close_servicenow_ticket(incident_id))

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

    return updated


@router.post("/api/incidents/{incident_id}/reject")
@limiter.limit("5/minute")
async def reject_incident(request: Request, incident_id: int, current_user: User = Depends(get_current_user)):
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    try:
        updated = update_incident_status(incident_id, status="REJECTED")
    except ValueError:
        raise HTTPException(status_code=404, detail="Incident not found during update")
    ACTIVE_APPROVALS.dec()
    try:
        from datetime import datetime, timezone

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
        detail="plan rejected"
    )
    create_notification(
        message=f"🚫 Incident #{incident_id} agent execution rejected by operator",
        type="warning",
        incident_id=incident_id,
    )

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

    return updated


@router.get("/api/incidents/approvals")
def list_pending_approvals(role: str | None = None, current_user: User = Depends(get_current_user)):
    return get_pending_approvals(role=role)

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
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
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
        if AI_PROVIDER == "ollama":
            raw = await call_ollama(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
        else:
            raw = await call_gemini(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
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
