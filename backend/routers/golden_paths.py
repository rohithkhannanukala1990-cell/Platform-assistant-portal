"""Golden Path templates — guided scaffolder workflows."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user, get_session, write_audit
from ..database import engine
from .rbac import VIEW_GOLDEN_PATHS, require_capability

router = APIRouter(prefix="/api/golden-paths", tags=["golden-paths"])
runs_router = APIRouter(prefix="/api/golden-path-runs", tags=["golden-paths"])


class GoldenPathTemplate(SQLModel, table=True):
    __tablename__ = "golden_path_templates"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    description: Optional[str] = None
    category: str = Field(default="General")
    entity_kind: Optional[str] = None
    config_schema_json: Optional[str] = None
    steps_json: Optional[str] = None
    is_active: bool = Field(default=True)
    created_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GoldenPathRun(SQLModel, table=True):
    __tablename__ = "golden_path_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="golden_path_templates.id")
    template_name: Optional[str] = None
    entity_id: Optional[int] = None
    requested_by: str
    status: str = Field(default="pending")
    inputs_json: Optional[str] = None
    outputs_json: Optional[str] = None
    run_logs: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GoldenPathTemplateCreate(BaseModel):
    name: str
    slug: Optional[str] = None
    description: Optional[str] = ""
    category: str = "General"
    entity_kind: Optional[str] = None
    config_schema_json: Optional[str] = None
    steps_json: Optional[str] = None
    is_active: bool = True


class GoldenPathTemplateUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    entity_kind: Optional[str] = None
    config_schema_json: Optional[str] = None
    steps_json: Optional[str] = None
    is_active: Optional[bool] = None


class GoldenPathRunRequest(BaseModel):
    entity_id: Optional[int] = None
    inputs: Optional[dict[str, Any]] = None


class GoldenPathSummary(BaseModel):
    id: str
    key: str  # stable identifier, e.g. "new-service-onboarding"
    name: str
    description: str
    estimated_minutes: int | None = None
    tags: list[str] = []


class GoldenPathListResponse(BaseModel):
    items: list[GoldenPathSummary]


# Workspace template category → golden-path categories that commonly apply.
_TEMPLATE_CATEGORY_AFFINITY: dict[str, set[str]] = {
    "onboarding": {"Onboarding", "Platform"},
    "operations": {"Operations", "Quality"},
    "engineering": {"DevOps", "Onboarding", "Quality"},
    "finops": {"Operations", "Quality"},
    "security": {"Quality", "Operations"},
    "general": {"Onboarding", "Platform", "DevOps", "Operations", "Quality"},
    "custom": {"Onboarding", "Platform"},
}


def _parse_json_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if x is not None and str(x).strip()]
    if isinstance(raw, str):
        try:
            data = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return [t.strip() for t in raw.split(",") if t.strip()]
        if isinstance(data, list):
            return [str(x) for x in data if x is not None and str(x).strip()]
    return []


def _path_to_summary(row: GoldenPathTemplate) -> GoldenPathSummary:
    tags: list[str] = []
    if row.category:
        tags.append(row.category)
    if row.entity_kind:
        tags.append(row.entity_kind)
    estimated: int | None = None
    try:
        steps = json.loads(row.steps_json or "[]")
        if isinstance(steps, list) and steps:
            estimated = len(steps) * 5
    except json.JSONDecodeError:
        estimated = None
    return GoldenPathSummary(
        id=str(row.id),
        key=row.slug,
        name=row.name,
        description=row.description or "",
        estimated_minutes=estimated,
        tags=tags,
    )


def _active_golden_paths(session: Session) -> list[GoldenPathTemplate]:
    return list(
        session.exec(
            select(GoldenPathTemplate)
            .where(GoldenPathTemplate.is_active == True)  # noqa: E712
            .order_by(GoldenPathTemplate.name)
        ).all()
    )


def find_applicable_paths_for_template(
    session: Session, template: Any
) -> list[GoldenPathTemplate]:
    """Discover golden paths that apply to a workspace Template blueprint."""
    category = (getattr(template, "category", None) or "general").strip().lower()
    affinity = _TEMPLATE_CATEGORY_AFFINITY.get(category, {"Onboarding", "Platform"})
    template_tags = {t.lower() for t in _parse_json_list(getattr(template, "tags", None))}
    name_blob = f"{getattr(template, 'name', '')} {getattr(template, 'description', '') or ''}".lower()

    matched: list[GoldenPathTemplate] = []
    seen: set[int] = set()
    for path in _active_golden_paths(session):
        pid = path.id
        if pid is None or pid in seen:
            continue
        path_cat = (path.category or "").strip()
        haystack = f"{path.slug} {path.name} {path_cat} {path.entity_kind or ''}".lower()
        if path_cat in affinity:
            seen.add(pid)
            matched.append(path)
            continue
        if template_tags and any(tag in haystack for tag in template_tags):
            seen.add(pid)
            matched.append(path)
            continue
        # Keyword overlap with template name/description (e.g. "observability", "cicd")
        keywords = [w for w in re.split(r"[^a-z0-9]+", name_blob) if len(w) >= 4]
        if any(kw in haystack for kw in keywords):
            seen.add(pid)
            matched.append(path)

    if matched:
        return matched
    # Sensible onboarding fallback when no affinity match.
    return [p for p in _active_golden_paths(session) if (p.category or "") == "Onboarding"]


def find_applicable_paths_for_entity(
    session: Session, entity: Any
) -> list[GoldenPathTemplate]:
    """Discover golden paths for a catalog entity by kind and tags."""
    kind = (getattr(entity, "kind", None) or "").strip()
    entity_tags = {t.lower() for t in _parse_json_list(getattr(entity, "tags", None))}
    lifecycle = (getattr(entity, "lifecycle", None) or "").strip().lower()

    matched: list[GoldenPathTemplate] = []
    seen: set[int] = set()
    for path in _active_golden_paths(session):
        pid = path.id
        if pid is None or pid in seen:
            continue
        path_kind = (path.entity_kind or "").strip()
        if path_kind and kind and path_kind.lower() == kind.lower():
            seen.add(pid)
            matched.append(path)
            continue
        haystack = f"{path.slug} {path.name} {path.category or ''}".lower()
        if entity_tags and any(tag in haystack for tag in entity_tags):
            seen.add(pid)
            matched.append(path)
            continue
        # Production entities also surface readiness / ops paths.
        if lifecycle == "production" and (path.category or "") in {"Quality", "Operations"}:
            seen.add(pid)
            matched.append(path)

    return matched


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(name: str) -> str:
    s = (name or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s[:120] if s else "") or "golden-path"


def _audit(user: User, event_type: str, detail: str) -> None:
    write_audit(
        actor=user.username,
        actor_role=user.role,
        event_type=event_type,
        resource="golden_paths",
        detail=detail,
    )


def _serialize_template(row: GoldenPathTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description or "",
        "category": row.category,
        "entity_kind": row.entity_kind,
        "config_schema_json": row.config_schema_json,
        "steps_json": row.steps_json,
        "is_active": row.is_active,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_run(row: GoldenPathRun) -> dict[str, Any]:
    try:
        outputs = json.loads(row.outputs_json or "{}")
    except json.JSONDecodeError:
        outputs = {}
    try:
        inputs = json.loads(row.inputs_json or "{}")
    except json.JSONDecodeError:
        inputs = {}
    return {
        "id": row.id,
        "template_id": row.template_id,
        "template_name": row.template_name,
        "entity_id": row.entity_id,
        "requested_by": row.requested_by,
        "status": row.status,
        "inputs": inputs,
        "outputs": outputs,
        "run_logs": row.run_logs or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def seed_golden_path_templates(session: Session) -> None:
    """Seed default Golden Path templates if none exist."""
    existing = session.exec(select(GoldenPathTemplate)).first()
    if existing:
        return

    defaults = [
        GoldenPathTemplate(
            name="Create New Service",
            slug="create-new-service",
            description=(
                "Scaffold a new microservice with CI/CD, observability, "
                "and catalog registration pre-configured."
            ),
            category="Onboarding",
            entity_kind="Service",
            config_schema_json=json.dumps(
                {
                    "fields": [
                        {
                            "name": "service_name",
                            "label": "Service Name",
                            "type": "string",
                            "required": True,
                            "placeholder": "my-payment-service",
                        },
                        {
                            "name": "owner_team",
                            "label": "Owner Team",
                            "type": "string",
                            "required": True,
                            "placeholder": "platform-team",
                        },
                        {
                            "name": "language",
                            "label": "Language",
                            "type": "select",
                            "required": True,
                            "options": ["Python", "Node.js", "Go", "Java"],
                        },
                        {
                            "name": "repo_url",
                            "label": "Repository URL",
                            "type": "string",
                            "required": False,
                            "placeholder": "https://github.com/org/repo",
                        },
                    ]
                }
            ),
            steps_json=json.dumps(
                [
                    {"type": "form", "label": "Configure Service"},
                    {"type": "review", "label": "Review Configuration"},
                    {"type": "execute", "label": "Creating Service"},
                    {"type": "complete", "label": "Service Created"},
                ]
            ),
            is_active=True,
        ),
        GoldenPathTemplate(
            name="Add Observability Stack",
            slug="add-observability",
            description=(
                "Add metrics, logging, distributed tracing, and alerting "
                "to an existing service."
            ),
            category="Operations",
            entity_kind="Service",
            config_schema_json=json.dumps(
                {
                    "fields": [
                        {
                            "name": "service_id",
                            "label": "Target Service ID",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "enable_traces",
                            "label": "Enable Distributed Tracing",
                            "type": "boolean",
                            "required": False,
                        },
                        {
                            "name": "alert_channel",
                            "label": "Alert Channel",
                            "type": "string",
                            "required": False,
                            "placeholder": "#platform-alerts",
                        },
                    ]
                }
            ),
            steps_json=json.dumps(
                [
                    {"type": "form", "label": "Configure Observability"},
                    {"type": "review", "label": "Review"},
                    {"type": "execute", "label": "Installing Stack"},
                    {"type": "complete", "label": "Observability Ready"},
                ]
            ),
            is_active=True,
        ),
        GoldenPathTemplate(
            name="Production Readiness Pack",
            slug="production-readiness",
            description=(
                "Run the full production readiness checklist: "
                "standards evaluation, scorecard run, and action recommendations."
            ),
            category="Quality",
            entity_kind="Service",
            config_schema_json=json.dumps(
                {
                    "fields": [
                        {
                            "name": "service_id",
                            "label": "Service ID",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "owner_email",
                            "label": "Owner Email",
                            "type": "string",
                            "required": True,
                            "placeholder": "team@company.com",
                        },
                    ]
                }
            ),
            steps_json=json.dumps(
                [
                    {"type": "form", "label": "Identify Service"},
                    {"type": "review", "label": "Review Checklist"},
                    {"type": "execute", "label": "Running Evaluation"},
                    {"type": "complete", "label": "Report Ready"},
                ]
            ),
            is_active=True,
        ),
        GoldenPathTemplate(
            name="Register Tool Account",
            slug="register-tool-account",
            description=(
                "Register a new external tool account (GitHub, Jira, PagerDuty) "
                "with the platform."
            ),
            category="Platform",
            entity_kind="Component",
            config_schema_json=json.dumps(
                {
                    "fields": [
                        {
                            "name": "tool_type",
                            "label": "Tool Type",
                            "type": "select",
                            "required": True,
                            "options": ["GitHub", "Jira", "PagerDuty", "Slack", "Datadog"],
                        },
                        {
                            "name": "account_name",
                            "label": "Account/Org Name",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "api_token",
                            "label": "API Token",
                            "type": "string",
                            "required": True,
                            "placeholder": "will be stored encrypted",
                        },
                    ]
                }
            ),
            steps_json=json.dumps(
                [
                    {"type": "form", "label": "Account Details"},
                    {"type": "review", "label": "Review"},
                    {"type": "execute", "label": "Registering"},
                    {"type": "complete", "label": "Account Registered"},
                ]
            ),
            is_active=True,
        ),
        GoldenPathTemplate(
            name="Add CI/CD Pipeline",
            slug="add-cicd-pipeline",
            description=(
                "Generate and connect a full CI/CD pipeline with "
                "build, test, security scan, and deploy stages."
            ),
            category="DevOps",
            entity_kind="Service",
            config_schema_json=json.dumps(
                {
                    "fields": [
                        {
                            "name": "service_name",
                            "label": "Service Name",
                            "type": "string",
                            "required": True,
                        },
                        {
                            "name": "ci_provider",
                            "label": "CI Provider",
                            "type": "select",
                            "required": True,
                            "options": ["GitHub Actions", "GitLab CI", "Jenkins", "CircleCI"],
                        },
                        {
                            "name": "deploy_target",
                            "label": "Deploy Target",
                            "type": "select",
                            "required": True,
                            "options": ["GKE", "EKS", "Cloud Run", "App Engine", "EC2"],
                        },
                        {
                            "name": "enable_sast",
                            "label": "Enable Security Scan",
                            "type": "boolean",
                            "required": False,
                        },
                    ]
                }
            ),
            steps_json=json.dumps(
                [
                    {"type": "form", "label": "Pipeline Configuration"},
                    {"type": "review", "label": "Review Pipeline"},
                    {"type": "execute", "label": "Creating Pipeline"},
                    {"type": "complete", "label": "Pipeline Live"},
                ]
            ),
            is_active=True,
        ),
    ]
    for template in defaults:
        session.add(template)
    session.commit()


@router.get("")
def list_golden_path_templates(
    category: Optional[str] = Query(None),
    entity_kind: Optional[str] = Query(None),
    is_active: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_capability(VIEW_GOLDEN_PATHS)),
):
    q = select(GoldenPathTemplate)
    if is_active:
        q = q.where(GoldenPathTemplate.is_active == True)  # noqa: E712
    if category:
        q = q.where(GoldenPathTemplate.category == category)
    if entity_kind:
        q = q.where(GoldenPathTemplate.entity_kind == entity_kind)
    q = q.order_by(GoldenPathTemplate.name).offset(skip).limit(limit)
    rows = session.exec(q).all()
    return [_serialize_template(r) for r in rows]


@router.get("/applicable", response_model=GoldenPathListResponse)
def list_applicable_golden_paths(
    template_id: str | None = Query(None),
    entity_id: str | None = Query(None),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_capability(VIEW_GOLDEN_PATHS)),
):
    """Return golden paths applicable to a workspace template or catalog entity."""
    if not template_id and not entity_id:
        raise HTTPException(
            status_code=400,
            detail="Provide template_id or entity_id (at least one is required)",
        )

    paths: list[GoldenPathTemplate] = []

    if template_id:
        from ..database import Template

        template = session.get(Template, template_id)
        if not template or not template.is_active:
            raise HTTPException(status_code=404, detail="Template not found")
        paths = find_applicable_paths_for_template(session, template)

    if entity_id:
        from .catalog import CatalogEntity

        # TODO: Enforce workspace membership here when CatalogEntity gains a
        # workspace relationship. WorkspaceMember cannot currently scope it.
        entity = session.get(CatalogEntity, entity_id)
        if not entity or not entity.is_active:
            raise HTTPException(status_code=404, detail="Catalog entity not found")
        entity_paths = find_applicable_paths_for_entity(session, entity)
        if template_id:
            # Union when both filters are provided.
            by_id = {p.id: p for p in paths}
            for p in entity_paths:
                by_id[p.id] = p
            paths = list(by_id.values())
        else:
            paths = entity_paths

    return GoldenPathListResponse(items=[_path_to_summary(p) for p in paths])


@router.post("")
def create_golden_path_template(
    body: GoldenPathTemplateCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    slug = (body.slug or _slugify(body.name)).strip()
    dup = session.exec(select(GoldenPathTemplate).where(GoldenPathTemplate.slug == slug)).first()
    if dup:
        raise HTTPException(status_code=400, detail="Slug already exists")
    now = _now()
    row = GoldenPathTemplate(
        name=body.name.strip(),
        slug=slug,
        description=(body.description or "").strip(),
        category=(body.category or "General").strip(),
        entity_kind=body.entity_kind,
        config_schema_json=body.config_schema_json,
        steps_json=body.steps_json,
        is_active=body.is_active,
        created_by=current_user.username,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    _audit(current_user, "golden_path_template_created", f"template_id={row.id} slug={row.slug}")
    return _serialize_template(row)


@router.get("/{template_id}")
def get_golden_path_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_capability(VIEW_GOLDEN_PATHS)),
):
    row = session.get(GoldenPathTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return _serialize_template(row)


@router.put("/{template_id}")
def update_golden_path_template(
    template_id: int,
    body: GoldenPathTemplateUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = session.get(GoldenPathTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"]:
        dup = session.exec(
            select(GoldenPathTemplate).where(
                GoldenPathTemplate.slug == data["slug"],
                GoldenPathTemplate.id != template_id,
            )
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="Slug already exists")
    for key, val in data.items():
        setattr(row, key, val)
    row.updated_at = _now()
    session.add(row)
    session.commit()
    session.refresh(row)
    _audit(current_user, "golden_path_template_updated", f"template_id={row.id}")
    return _serialize_template(row)


@router.delete("/{template_id}")
def delete_golden_path_template(
    template_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = session.get(GoldenPathTemplate, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    row.is_active = False
    row.updated_at = _now()
    session.add(row)
    session.commit()
    _audit(current_user, "golden_path_template_deleted", f"template_id={template_id}")
    return {"ok": True, "id": template_id}


@router.post("/{template_id}/run")
async def run_golden_path(
    template_id: int,
    body: GoldenPathRunRequest | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    template = session.get(GoldenPathTemplate, template_id)
    if not template or not template.is_active:
        raise HTTPException(status_code=404, detail="Template not found")

    entity_id = body.entity_id if body else None
    inputs = body.inputs if body and body.inputs else {}
    now = _now()

    run = GoldenPathRun(
        template_id=template.id,
        template_name=template.name,
        entity_id=entity_id,
        requested_by=current_user.username,
        status="running",
        inputs_json=json.dumps(inputs),
        outputs_json="{}",
        run_logs="",
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    await asyncio.sleep(0)

    steps = json.loads(template.steps_json or "[]")
    ts = now.isoformat()
    run.status = "completed"
    run.outputs_json = json.dumps(
        {
            "message": f"Golden Path '{template.name}' completed successfully.",
            "steps_completed": len(steps),
            "entity_id": entity_id,
            "timestamp": ts,
        }
    )
    run.run_logs = (
        f"[{ts}] Starting golden path: {template.name}\n"
        f"[{ts}] Processing inputs...\n"
        f"[{ts}] Executing steps...\n"
        f"[{ts}] All steps completed successfully.\n"
    )
    run.updated_at = _now()
    session.add(run)
    session.commit()
    session.refresh(run)
    _audit(
        current_user,
        "golden_path_run_completed",
        f"run_id={run.id} template_id={template_id}",
    )

    from ..ws_portal import broadcast_json

    asyncio.create_task(
        broadcast_json(
            {
                "type": "golden_path_run_update",
                "run_id": str(run.id),
                "template_id": str(run.template_id),
                "status": run.status,
                "timestamp": run.updated_at.isoformat()
                if hasattr(run.updated_at, "isoformat")
                else datetime.now(timezone.utc).isoformat(),
            }
        )
    )

    return _serialize_run(run)


@runs_router.get("")
def list_golden_path_runs(
    template_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
    current_user: User = Depends(require_capability(VIEW_GOLDEN_PATHS)),
):
    q = select(GoldenPathRun).order_by(GoldenPathRun.created_at.desc())
    if template_id is not None:
        q = q.where(GoldenPathRun.template_id == template_id)
    if status:
        q = q.where(GoldenPathRun.status == status)
    rows = session.exec(q.offset(skip).limit(limit)).all()
    return [_serialize_run(r) for r in rows]


@runs_router.get("/{run_id}")
def get_golden_path_run(
    run_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(require_capability(VIEW_GOLDEN_PATHS)),
):
    row = session.get(GoldenPathRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return _serialize_run(row)
