"""Software catalog API — services, APIs, libraries, websites."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user
from ..database import engine

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class CatalogEntity(SQLModel, table=True):
    __tablename__ = "catalog_entities"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    kind: str  # Service | API | Library | Website
    lifecycle: str  # experimental | production | deprecated
    owner_team: str
    language: Optional[str] = None
    repo_url: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None  # JSON string of list
    health_status: str = "unknown"  # healthy | degraded | unknown
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: int = 1


class CatalogCreate(BaseModel):
    name: str
    kind: str
    lifecycle: str
    owner_team: str
    language: Optional[str] = None
    repo_url: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    health_status: Optional[str] = "unknown"


class CatalogUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    lifecycle: Optional[str] = None
    owner_team: Optional[str] = None
    language: Optional[str] = None
    repo_url: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    health_status: Optional[str] = None


def _tags_parse(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _serialize(row: CatalogEntity) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "lifecycle": row.lifecycle,
        "owner_team": row.owner_team,
        "language": row.language,
        "repo_url": row.repo_url,
        "description": row.description or "",
        "tags": _tags_parse(row.tags),
        "tags_raw": row.tags,
        "health_status": row.health_status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_active": bool(row.is_active),
    }


def _get_active(session: Session, entity_id: str) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return row


@router.get("")
def list_catalog(
    kind: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    owner_team: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        q = select(CatalogEntity).where(CatalogEntity.is_active == 1)
        if kind:
            q = q.where(CatalogEntity.kind == kind)
        if lifecycle:
            q = q.where(CatalogEntity.lifecycle == lifecycle)
        if owner_team:
            q = q.where(CatalogEntity.owner_team == owner_team)
        q = q.order_by(CatalogEntity.name.asc())
        rows = session.exec(q).all()
        return [_serialize(r) for r in rows]


@router.post("")
def create_catalog(body: CatalogCreate, current_user: User = Depends(get_current_user)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    with Session(engine) as session:
        row = CatalogEntity(
            id=str(uuid.uuid4()),
            name=name,
            kind=body.kind.strip(),
            lifecycle=body.lifecycle.strip(),
            owner_team=body.owner_team.strip(),
            language=(body.language or "").strip() or None,
            repo_url=(body.repo_url or "").strip() or None,
            description=(body.description or "").strip() or None,
            tags=body.tags,
            health_status=(body.health_status or "unknown").strip(),
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize(row)


@router.get("/{entity_id}")
def get_catalog(entity_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        return _serialize(_get_active(session, entity_id))


@router.put("/{entity_id}")
def update_catalog(
    entity_id: str,
    body: CatalogUpdate,
    current_user: User = Depends(get_current_user),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    with Session(engine) as session:
        row = _get_active(session, entity_id)
        if "name" in data and data["name"] is not None:
            row.name = str(data["name"]).strip()
        if "kind" in data and data["kind"] is not None:
            row.kind = str(data["kind"]).strip()
        if "lifecycle" in data and data["lifecycle"] is not None:
            row.lifecycle = str(data["lifecycle"]).strip()
        if "owner_team" in data and data["owner_team"] is not None:
            row.owner_team = str(data["owner_team"]).strip()
        if "language" in data:
            row.language = str(data["language"]).strip() if data["language"] else None
        if "repo_url" in data:
            row.repo_url = str(data["repo_url"]).strip() if data["repo_url"] else None
        if "description" in data:
            row.description = str(data["description"]).strip() if data["description"] else None
        if "tags" in data:
            row.tags = data["tags"]
        if "health_status" in data and data["health_status"] is not None:
            row.health_status = str(data["health_status"]).strip()
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize(row)


@router.delete("/{entity_id}")
def delete_catalog(entity_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        row = _get_active(session, entity_id)
        row.is_active = 0
        session.add(row)
        session.commit()
    return {"deleted": True}
