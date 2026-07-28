"""Read-only PagerDuty operations for the authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import User, get_current_user
from ..connectors.pagerduty_connector import PagerDutyConnector
from ..services.pagerduty_access import pagerduty_connector_for_user

router = APIRouter(prefix="/api/pagerduty", tags=["pagerduty"])


def _connector(user: User) -> PagerDutyConnector:
    return pagerduty_connector_for_user(user)


@router.get("/incidents")
async def api_pagerduty_incidents(
    status: str = Query(default="triggered,acknowledged"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    connector = _connector(current_user)
    return await connector.list_incidents(status=status, limit=limit)


@router.get("/oncalls")
async def api_pagerduty_oncalls(
    limit: int = Query(default=20, ge=1, le=100),
    schedule_id: str | None = Query(default=None),
    service: str | None = Query(default=None, description="PagerDuty service id"),
    current_user: User = Depends(get_current_user),
):
    connector = _connector(current_user)
    return await connector.list_oncalls(
        limit=limit,
        schedule_id=schedule_id,
        service_id=service,
    )
