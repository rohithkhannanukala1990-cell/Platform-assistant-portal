"""Software catalog API — services, APIs, libraries, websites."""

from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import Index
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user
from ..database import engine, get_db
from backend.middleware.rbac_middleware import require_permission
from ..services.isolation import apply_tenant_filter, assert_same_tenant, require_tenant

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class CatalogEntity(SQLModel, table=True):
    __tablename__ = "catalog_entities"
    __table_args__ = (Index("ix_catalog_name_type", "name", "kind"),)

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
    tenant_id: Optional[str] = Field(default="default", index=True)


class ServiceDependency(SQLModel, table=True):
    __tablename__ = "service_dependencies"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    from_entity_id: str
    to_entity_id: str
    dep_type: str = "calls"  # calls | uses | depends_on
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class DependencyCreate(BaseModel):
    from_entity_id: str
    to_entity_id: str
    dep_type: str = "calls"


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


class CatalogSearchResult(BaseModel):
    id: str
    name: str
    type: str
    owner: str
    description: str = ""
    tags: list[str] = []


class PaginatedCatalogResults(BaseModel):
    items: list[CatalogSearchResult]
    total: int
    page: int
    per_page: int
    pages: int


# TODO: Support tag-based filters (contains any of requested tags) for catalog listings
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
        "tenant_id": getattr(row, "tenant_id", None) or "default",
    }


def _get_active(
    session: Session,
    entity_id: str,
    *,
    tenant_id: str | None = None,
) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Entity not found")
    if tenant_id is not None:
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
    return row


def _entity_name_map(session: Session) -> dict[str, str]:
    rows = session.exec(select(CatalogEntity).where(CatalogEntity.is_active == 1)).all()
    return {r.id: r.name for r in rows}


def _serialize_dependency(row: ServiceDependency, names: dict[str, str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "from_entity_id": row.from_entity_id,
        "to_entity_id": row.to_entity_id,
        "dep_type": row.dep_type,
        "from_name": names.get(row.from_entity_id, row.from_entity_id),
        "to_name": names.get(row.to_entity_id, row.to_entity_id),
    }


_VALID_DEP_TYPES = frozenset({"calls", "uses", "depends_on"})


# TODO: Add filters for owner_team, lifecycle, environment, and tags to the catalog list endpoint
@router.get("")
def list_catalog(
    request: Request,
    kind: Optional[str] = Query(None),
    lifecycle: Optional[str] = Query(None),
    owner_team: Optional[str] = Query(None),
    tags: list[str] | None = Query(
        None,
        description="Return entities containing any requested tag; repeat the parameter",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    from ..services.pagination import clamp_page

    tenant_id = require_tenant(request)
    _, size, offset = clamp_page(page, page_size)
    with Session(engine) as session:
        q = select(CatalogEntity).where(CatalogEntity.is_active == 1)
        q = apply_tenant_filter(q, CatalogEntity, tenant_id)
        if kind:
            q = q.where(CatalogEntity.kind == kind)
        if lifecycle:
            q = q.where(CatalogEntity.lifecycle == lifecycle)
        if owner_team:
            q = q.where(CatalogEntity.owner_team == owner_team)
        q = q.order_by(CatalogEntity.name.asc())
        requested_tags = {
            tag.strip().lower()
            for value in (tags or [])
            for tag in value.split(",")
            if tag.strip()
        }
        if requested_tags:
            rows = session.exec(q).all()
            rows = [
                row
                for row in rows
                if requested_tags.intersection(
                    tag.lower() for tag in _tags_parse(row.tags)
                )
            ]
            rows = rows[offset : offset + size]
        else:
            rows = session.exec(q.offset(offset).limit(size)).all()
        return [_serialize(r) for r in rows]


@router.get("/dependencies")
def list_dependencies(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        names = _entity_name_map(session)
        entity_ids = {
            e.id
            for e in session.exec(
                select(CatalogEntity).where(
                    CatalogEntity.is_active == 1,
                    CatalogEntity.tenant_id == tenant_id,
                )
            ).all()
        }
        rows = session.exec(select(ServiceDependency).order_by(ServiceDependency.created_at.desc())).all()
        return [
            _serialize_dependency(r, names)
            for r in rows
            if r.from_entity_id in entity_ids and r.to_entity_id in entity_ids
        ]


@router.post("/dependencies")
def create_dependency(
    request: Request,
    body: DependencyCreate,
    current_user: User = Depends(get_current_user),
):
    dep_type = (body.dep_type or "calls").strip()
    if dep_type not in _VALID_DEP_TYPES:
        raise HTTPException(status_code=400, detail="dep_type must be calls, uses, or depends_on")
    if body.from_entity_id == body.to_entity_id:
        raise HTTPException(status_code=400, detail="from and to must differ")
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        _get_active(session, body.from_entity_id, tenant_id=tenant_id)
        _get_active(session, body.to_entity_id, tenant_id=tenant_id)
        names = _entity_name_map(session)
        row = ServiceDependency(
            id=str(uuid.uuid4()),
            from_entity_id=body.from_entity_id,
            to_entity_id=body.to_entity_id,
            dep_type=dep_type,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize_dependency(row, names)


@router.delete("/dependencies/{dep_id}")
def delete_dependency(
    request: Request,
    dep_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.get(ServiceDependency, dep_id)
        if not row:
            raise HTTPException(status_code=404, detail="Dependency not found")
        _get_active(session, row.from_entity_id, tenant_id=tenant_id)
        _get_active(session, row.to_entity_id, tenant_id=tenant_id)
        session.delete(row)
        session.commit()
    return {"ok": True}


@router.get("/search", response_model=PaginatedCatalogResults)
def search_catalog(
    request: Request,
    q: str = Query(default="", description="Search term"),
    type: str = Query(default="", description="Entity type filter"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Paginated catalog search. Declared before /{entity_id} so 'search' is not captured as an id."""
    tenant_id = require_tenant(request)
    q_obj = db.query(CatalogEntity).filter(
        CatalogEntity.is_active == 1,
        CatalogEntity.tenant_id == tenant_id,
    )
    if q:
        q_obj = q_obj.filter(CatalogEntity.name.ilike(f"%{q}%"))
    if type:
        q_obj = q_obj.filter(CatalogEntity.kind == type)

    total = q_obj.count()
    rows = q_obj.offset((page - 1) * per_page).limit(per_page).all()
    pages = math.ceil(total / per_page) if per_page else 0

    items = [
        CatalogSearchResult(
            id=row.id,
            name=row.name,
            type=row.kind,
            owner=row.owner_team,
            description=row.description or "",
            tags=_tags_parse(row.tags),
        )
        for row in rows
    ]
    return PaginatedCatalogResults(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


# TODO: Protect catalog mutations with require_permission("catalog", "write")
@router.post("")
def create_catalog(
    request: Request,
    body: CatalogCreate,
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_permission("catalog", "write")),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    tenant_id = require_tenant(request)
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
            tenant_id=tenant_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize(row)


@router.get("/{entity_id}/dependencies")
def list_entity_dependencies(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        _get_active(session, entity_id, tenant_id=tenant_id)
        names = _entity_name_map(session)
        rows = session.exec(
            select(ServiceDependency).where(
                (ServiceDependency.from_entity_id == entity_id)
                | (ServiceDependency.to_entity_id == entity_id)
            )
        ).all()
        return [_serialize_dependency(r, names) for r in rows]


@router.get("/{entity_id}")
def get_catalog(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        return _serialize(_get_active(session, entity_id, tenant_id=tenant_id))


# TODO: Protect catalog mutations with require_permission("catalog", "write")
@router.put("/{entity_id}")
def update_catalog(
    request: Request,
    entity_id: str,
    body: CatalogUpdate,
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_permission("catalog", "write")),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = _get_active(session, entity_id, tenant_id=tenant_id)
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


# TODO: Protect catalog mutations with require_permission("catalog", "write")
# TODO: Prevent deletion of entities that have dependencies in ServiceDependency, or require explicit force flag
@router.delete("/{entity_id}")
def delete_catalog(
    request: Request,
    entity_id: str,
    force: bool = Query(
        False,
        description="Delete dependency edges before deactivating the entity",
    ),
    current_user: User = Depends(get_current_user),
    _perm: None = Depends(require_permission("catalog", "write")),
):
    with Session(engine) as session:
        row = _get_active(session, entity_id, tenant_id=require_tenant(request))
        dependencies = list(
            session.exec(
                select(ServiceDependency).where(
                    (ServiceDependency.from_entity_id == entity_id)
                    | (ServiceDependency.to_entity_id == entity_id)
                )
            ).all()
        )
        if dependencies and not force:
            raise HTTPException(
                status_code=400,
                detail="Entity has dependencies, cannot delete without force=true",
            )
        for dependency in dependencies:
            session.delete(dependency)
        row.is_active = 0
        session.add(row)
        session.commit()
    return {
        "deleted": True,
        "dependencies_deleted": len(dependencies),
    }
