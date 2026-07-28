"""Outbound webhook ops — deliver portal events to customer URL."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import User, get_current_user, write_audit
from ..connectors.outbound_webhook_connector import OutboundWebhookConnector
from ..services.outbound_webhook_access import outbound_webhook_connector_for_user

router = APIRouter(prefix="/api/outbound-webhook", tags=["outbound-webhook"])


def _connector(user: User) -> OutboundWebhookConnector:
    return outbound_webhook_connector_for_user(user)


class DeliverBody(BaseModel):
    event: str = "custom"
    payload: Optional[dict[str, Any]] = None
    approved: bool = False


@router.get("/status")
async def api_outbound_webhook_status(current_user: User = Depends(get_current_user)):
    """Read-only connectivity check (does not POST)."""
    result = await _connector(current_user).ping()
    return result


@router.post("/deliver")
async def api_outbound_webhook_deliver(
    body: DeliverBody,
    current_user: User = Depends(get_current_user),
):
    """Deliver an event. Non-admins need HITL approved=true."""
    if (current_user.role or "") != "Admin" and not body.approved:
        raise HTTPException(
            status_code=403,
            detail="Outbound webhook deliver requires Admin or HITL approval (approved=true)",
        )
    result = await _connector(current_user).deliver(body.event, body.payload or {})
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="outbound_webhook_deliver",
        resource="outbound_webhook",
        detail=f"event={body.event} ok={result.get('ok')}",
    )
    return result
