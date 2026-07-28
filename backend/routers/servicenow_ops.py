"""ServiceNow ops — create incident via webhook (HITL write)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import User, get_current_user, write_audit
from ..connectors.servicenow_connector import ServiceNowConnector
from ..services.servicenow_access import servicenow_connector_for_user

router = APIRouter(prefix="/api/servicenow", tags=["servicenow"])


def _connector(user: User) -> ServiceNowConnector:
    return servicenow_connector_for_user(user)


class CreateIncidentBody(BaseModel):
    short_description: str
    description: str = ""
    urgency: str = "2"
    approved: bool = False


@router.get("/status")
async def api_servicenow_status(current_user: User = Depends(get_current_user)):
    return await _connector(current_user).ping()


@router.post("/incidents")
async def api_servicenow_create_incident(
    body: CreateIncidentBody,
    current_user: User = Depends(get_current_user),
):
    if (current_user.role or "") != "Admin" and not body.approved:
        raise HTTPException(
            status_code=403,
            detail="ServiceNow incident create requires Admin or HITL approval (approved=true)",
        )
    if not (body.short_description or "").strip():
        raise HTTPException(status_code=400, detail="short_description is required")
    result = await _connector(current_user).create_incident(
        short_description=body.short_description,
        description=body.description,
        urgency=body.urgency,
    )
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="servicenow_incident_create",
        resource="servicenow",
        detail=f"ok={result.get('ok')}",
    )
    return result
