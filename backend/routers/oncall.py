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
    schedule_ids: list[str] | None = Query(
        default=None, description="Multiple PagerDuty schedule ids (repeat param)"
    ),
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

    ids: list[str] = []
    if schedule_ids:
        ids.extend([s for s in schedule_ids if s and str(s).strip()])
    if schedule_id and schedule_id not in ids:
        ids.append(schedule_id)

    oncalls: list[dict] = []
    if ids:
        for sid in ids:
            rows = await connector.list_oncalls(
                limit=limit,
                schedule_id=sid,
                service_id=service,
            )
            for row in rows:
                if isinstance(row, dict):
                    row = {**row, "schedule_id": row.get("schedule_id") or sid}
                oncalls.append(row)
    else:
        oncalls = await connector.list_oncalls(
            limit=limit,
            schedule_id=None,
            service_id=service,
        )

    # Group by schedule for multi-schedule UX.
    by_schedule: dict[str, list] = {}
    for row in oncalls:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("schedule_id") or row.get("schedule") or "unknown")
        by_schedule.setdefault(sid, []).append(row)

    pd_url = PD_SCHEDULES_URL
    if len(ids) == 1:
        pd_url = f"{PD_SCHEDULES_URL}/{ids[0]}"

    return {
        "source": "pagerduty",
        "scheduling_in": "pagerduty",
        "scheduling_note": "On-call scheduling and overrides remain in PagerDuty.",
        "pd_url": pd_url,
        "oncalls": oncalls,
        "schedules": [
            {"schedule_id": sid, "oncalls": rows, "pd_url": f"{PD_SCHEDULES_URL}/{sid}"}
            for sid, rows in by_schedule.items()
        ],
        "filters": {
            "service": service,
            "schedule_id": schedule_id,
            "schedule_ids": ids or None,
        },
        "empty": len(oncalls) == 0,
    }
