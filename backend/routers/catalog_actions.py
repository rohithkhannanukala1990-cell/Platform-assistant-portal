"""Catalog self-service actions API (Phase G6)."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..auth import User, get_current_user, write_audit
from ..database import engine
from ..routers.catalog import CatalogEntity
from ..services.catalog_actions import (
    execute_catalog_action,
    get_catalog_action,
    list_catalog_actions,
    serialize_catalog_action,
)
from ..services.isolation import require_tenant

router = APIRouter(tags=["catalog-actions"])


class ExecuteBody(BaseModel):
    entity_id: str
    inputs: Optional[dict[str, Any]] = None


def _get_entity(session: Session, entity_id: str, tenant_id: str) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    ent_tenant = getattr(row, "tenant_id", None) or "default"
    if ent_tenant != tenant_id:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return row


@router.get("/api/catalog-actions")
def api_list_catalog_actions(
    request: Request,
    entity_kind: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    return list_catalog_actions(tenant_id=tenant_id, entity_kind=entity_kind)


@router.get("/api/catalog/{entity_id}/catalog-actions")
def api_list_entity_catalog_actions(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        entity = _get_entity(session, entity_id, tenant_id)
        kind = entity.kind
    return list_catalog_actions(tenant_id=tenant_id, entity_kind=kind)


@router.post("/api/catalog-actions/{action_id}/execute")
async def api_execute_catalog_action(
    request: Request,
    action_id: str,
    body: ExecuteBody,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    action = get_catalog_action(action_id, tenant_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    with Session(engine) as session:
        entity = _get_entity(session, body.entity_id, tenant_id)
        if action.entity_kind not in ("all", "") and action.entity_kind != entity.kind:
            raise HTTPException(status_code=400, detail="Action not applicable to this entity kind")
        # Detach attributes we need after session closes
        entity_snapshot = CatalogEntity(
            id=entity.id,
            name=entity.name,
            kind=entity.kind,
            lifecycle=entity.lifecycle,
            owner_team=entity.owner_team,
            language=entity.language,
            repo_url=entity.repo_url,
            description=entity.description,
            tags=entity.tags,
            health_status=entity.health_status,
            tenant_id=getattr(entity, "tenant_id", None) or tenant_id,
            is_active=entity.is_active,
        )

    result = await execute_catalog_action(
        action=action,
        entity=entity_snapshot,
        user=current_user,
        tenant_id=tenant_id,
        inputs=body.inputs,
    )
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="catalog_action_executed",
        resource=f"catalog_action:{action_id}",
        detail=f"entity={body.entity_id} status={result.get('status')} type={action.action_type}",
    )
    return {
        "action": serialize_catalog_action(action),
        "result": result,
    }
