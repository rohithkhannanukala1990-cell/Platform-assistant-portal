"""Slack ops — list channels (read) + notify (HITL / Admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth import User, get_current_user, write_audit
from ..connectors.slack_connector import SlackConnector
from ..services.slack_access import slack_connector_for_user

router = APIRouter(prefix="/api/slack", tags=["slack"])


def _connector(user: User) -> SlackConnector:
    return slack_connector_for_user(user)


def _can_notify(user: User, *, approved: bool) -> bool:
    if (user.role or "") == "Admin":
        return True
    # Explicit HITL approval flag from an approved agent/run flow.
    return bool(approved)


class NotifyBody(BaseModel):
    text: str
    channel: str | None = None
    approved: bool = False


@router.get("/channels")
async def api_slack_channels(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    return await _connector(current_user).list_channels(limit=limit)


@router.post("/notify")
async def api_slack_notify(
    body: NotifyBody,
    current_user: User = Depends(get_current_user),
):
    if not _can_notify(current_user, approved=body.approved):
        raise HTTPException(
            status_code=403,
            detail="Slack notify requires Admin or HITL approval (approved=true)",
        )
    if not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="text is required")
    result = await _connector(current_user).notify_channel(text=body.text, channel=body.channel)
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="slack_notify",
        resource="slack",
        detail=f"ok={result.get('ok')} mode={result.get('mode')}",
    )
    return result
