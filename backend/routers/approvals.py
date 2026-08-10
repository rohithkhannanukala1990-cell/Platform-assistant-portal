"""Unified approvals inbox — GET /api/approvals/inbox aggregates every pending
human-approval source; approve/reject/bulk-approve route to the existing
per-source service functions in ``services/unified_approvals.py`` (never
reimplemented here — this router is a thin HTTP wrapper).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from ..auth import User, get_current_user, require_admin
from ..services.isolation import require_tenant
from ..services.unified_approvals import (
    approve_item,
    bulk_approve,
    list_inbox_items,
    reject_item,
)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("/inbox")
def get_inbox(
    request: Request,
    risk: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    service: Optional[str] = Query(None),
    min_age_seconds: Optional[int] = Query(None, ge=0),
    sort: str = Query("age", pattern="^(age|risk)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sla_minutes: int = Query(30, ge=1, le=1440),
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return list_inbox_items(
        tenant_id,
        risk=risk,
        source=source,
        service=service,
        min_age_seconds=min_age_seconds,
        sort=sort,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        sla_minutes=sla_minutes,
    )


class ApproveBody(BaseModel):
    confirmation: Optional[str] = None


class RejectBody(BaseModel):
    reason: Optional[str] = None


class BulkApproveBody(BaseModel):
    ids: list[str]


@router.post("/{item_id}/approve")
async def approve_inbox_item(
    request: Request,
    item_id: str,
    body: ApproveBody | None = None,
    current_user: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    return await approve_item(
        item_id, tenant_id, current_user, confirmation=(body.confirmation if body else None)
    )


@router.post("/{item_id}/reject")
async def reject_inbox_item(
    request: Request,
    item_id: str,
    body: RejectBody | None = None,
    current_user: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    return await reject_item(item_id, tenant_id, current_user, reason=(body.reason if body else None))


@router.post("/bulk-approve")
async def bulk_approve_inbox_items(
    request: Request,
    body: BulkApproveBody,
    current_user: User = Depends(require_admin),
):
    tenant_id = require_tenant(request)
    if not body.ids:
        raise HTTPException(status_code=400, detail="ids must be a non-empty list")
    if len(body.ids) > 100:
        raise HTTPException(status_code=400, detail="Cannot bulk-approve more than 100 items at once")
    return await bulk_approve(body.ids, tenant_id, current_user)
