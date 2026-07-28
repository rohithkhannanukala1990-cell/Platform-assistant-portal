"""On-call visibility via PagerDuty (scheduling remains in PagerDuty)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from ..auth import User, get_current_user
from ..services.isolation import require_tenant
from ..services.pagerduty_access import pagerduty_connector_for_user

router = APIRouter(prefix="/api/oncall", tags=["oncall"])

PD_SCHEDULES_URL = "https://app.pagerduty.com/schedules"


@router.get("/now")
async def oncall_now(
    request: Request,
    service: str | None = Query(default=None, description="PagerDuty service id or name filter"),
    schedule_id: str | None = Query(default=None, description="PagerDuty schedule id"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Who is on-call now — sourced from PagerDuty schedules/services."""
    tenant_id = require_tenant(request)
    connector = pagerduty_connector_for_user(
        current_user,
        tenant_id=tenant_id,
        workspace_id=getattr(request.state, "workspace_id", None),
    )
    oncalls = await connector.list_oncalls(
        limit=limit,
        schedule_id=schedule_id,
        service_id=service,
    )
    pd_url = PD_SCHEDULES_URL
    if schedule_id:
        pd_url = f"{PD_SCHEDULES_URL}/{schedule_id}"
    return {
        "source": "pagerduty",
        "scheduling_in": "pagerduty",
        "scheduling_note": "On-call scheduling and overrides remain in PagerDuty.",
        "pd_url": pd_url,
        "oncalls": oncalls,
        "filters": {"service": service, "schedule_id": schedule_id},
    }
