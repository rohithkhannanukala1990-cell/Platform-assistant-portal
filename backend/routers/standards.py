"""Production readiness standards — entity compliance evaluation."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user, require_admin
from ..database import engine
from .catalog import CatalogEntity

router = APIRouter(prefix="/api/standards", tags=["standards"])
catalog_router = APIRouter(prefix="/api/catalog", tags=["standards"])


class Standard(SQLModel, table=True):
    __tablename__ = "standards"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    slug: str
    description: str = ""
    version: str = "1.0"
    applies_to_kind: str = "all"  # all | Service | API | Library
    is_active: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StandardCheck(SQLModel, table=True):
    __tablename__ = "standard_checks"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    standard_id: str = Field(foreign_key="standards.id", index=True)
    name: str
    description: str = ""
    weight: int = 10
    severity: str = "warn"
    rule_field: str = ""
    rule_operator: str = ""


class EntityStandardEvaluation(SQLModel, table=True):
    __tablename__ = "entity_standard_evaluations"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    entity_id: str = Field(foreign_key="catalog_entities.id", index=True)
    standard_id: str = Field(foreign_key="standards.id", index=True)
    overall_score: int = 0
    status: str = "unknown"
    results_json: str = "[]"
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StandardCreate(BaseModel):
    name: str
    slug: str
    description: str = ""
    version: str = "1.0"
    applies_to_kind: str = "all"


def _get_active_entity(session: Session, entity_id: str) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return row


def _field_value(entity: CatalogEntity, field_name: str) -> Any:
    return getattr(entity, field_name, None)


def _is_empty_value(val: Any) -> bool:
    if val is None:
        return True
    text = str(val).strip()
    return text == "" or text in ("[]", "null", "{}")


def _evaluate_check(entity: CatalogEntity, check: StandardCheck) -> dict[str, Any]:
    val = _field_value(entity, check.rule_field)
    op = (check.rule_operator or "").strip().lower()
    passed = False

    if op == "exists":
        passed = val is not None
    elif op == "not_empty":
        passed = not _is_empty_value(val)
    elif op == "equals":
        passed = val is not None and str(val) == check.description
    elif op == "not_equals":
        passed = val is not None and str(val) != check.description
    else:
        passed = False

    return {
        "check_id": check.id,
        "name": check.name,
        "rule_field": check.rule_field,
        "rule_operator": check.rule_operator,
        "severity": check.severity,
        "weight": check.weight,
        "passed": passed,
        "actual_value": val if val is not None else None,
        "expected": check.description or None,
    }


def _compute_score_and_status(results: list[dict[str, Any]]) -> tuple[int, str]:
    total_weight = sum(int(r.get("weight") or 0) for r in results)
    if total_weight <= 0:
        return 0, "unknown"
    earned = sum(int(r.get("weight") or 0) for r in results if r.get("passed"))
    overall = round((earned / total_weight) * 100)
    if overall >= 80:
        status = "pass"
    elif overall >= 50:
        status = "warn"
    else:
        status = "fail"
    return overall, status


def _serialize_standard(row: Standard, check_count: int = 0) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "description": row.description or "",
        "version": row.version,
        "applies_to_kind": row.applies_to_kind,
        "is_active": bool(row.is_active),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "check_count": check_count,
    }


def _serialize_evaluation(row: EntityStandardEvaluation) -> dict[str, Any]:
    try:
        results = json.loads(row.results_json or "[]")
        if not isinstance(results, list):
            results = []
    except json.JSONDecodeError:
        results = []
    return {
        "id": row.id,
        "entity_id": row.entity_id,
        "standard_id": row.standard_id,
        "overall_score": row.overall_score,
        "status": row.status,
        "results": results,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }


def seed_production_readiness_standard(session: Session) -> None:
    existing = session.exec(
        select(Standard).where(Standard.slug == "prod-readiness-v1")
    ).first()
    if existing:
        standard = existing
    else:
        standard = Standard(
            id=str(uuid.uuid4()),
            name="Production Readiness v1",
            slug="prod-readiness-v1",
            description="Baseline production readiness checks for catalog entities.",
            version="1.0",
            applies_to_kind="all",
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(standard)
        session.commit()
        session.refresh(standard)

    seed_checks = [
        ("Has description", "description", "not_empty", 15, "warn", ""),
        ("Has repo URL", "repo_url", "not_empty", 15, "warn", ""),
        ("Lifecycle is declared", "lifecycle", "not_empty", 10, "warn", ""),
        ("Not in experimental", "lifecycle", "not_equals", 10, "warn", "experimental"),
        ("Language declared", "language", "not_empty", 10, "warn", ""),
        ("Health status known", "health_status", "not_equals", 15, "fail", "unknown"),
        ("Owner team assigned", "owner_team", "not_empty", 15, "fail", ""),
        ("Has tags", "tags", "not_empty", 10, "warn", ""),
    ]

    for name, rule_field, rule_operator, weight, severity, desc in seed_checks:
        exists = session.exec(
            select(StandardCheck).where(
                StandardCheck.standard_id == standard.id,
                StandardCheck.name == name,
            )
        ).first()
        if exists:
            continue
        session.add(
            StandardCheck(
                id=str(uuid.uuid4()),
                standard_id=standard.id,
                name=name,
                description=desc,
                weight=weight,
                severity=severity,
                rule_field=rule_field,
                rule_operator=rule_operator,
            )
        )
    session.commit()


def _run_evaluation(
    session: Session, entity: CatalogEntity, standard: Standard
) -> EntityStandardEvaluation:
    checks = session.exec(
        select(StandardCheck).where(StandardCheck.standard_id == standard.id)
    ).all()

    if standard.applies_to_kind not in ("all", "") and entity.kind != standard.applies_to_kind:
        results: list[dict[str, Any]] = []
        overall_score = 0
        status = "unknown"
    else:
        results = [_evaluate_check(entity, c) for c in checks]
        overall_score, status = _compute_score_and_status(results)

    for old in session.exec(
        select(EntityStandardEvaluation).where(
            EntityStandardEvaluation.entity_id == entity.id,
            EntityStandardEvaluation.standard_id == standard.id,
        )
    ).all():
        session.delete(old)

    row = EntityStandardEvaluation(
        id=str(uuid.uuid4()),
        entity_id=entity.id,
        standard_id=standard.id,
        overall_score=overall_score,
        status=status,
        results_json=json.dumps(results),
        evaluated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


@router.get("")
def list_standards(current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(
            select(Standard).where(Standard.is_active == 1).order_by(Standard.name)
        ).all()
        out = []
        for s in rows:
            count = len(
                session.exec(
                    select(StandardCheck).where(StandardCheck.standard_id == s.id)
                ).all()
            )
            out.append(_serialize_standard(s, check_count=count))
        return out


@router.get("/{standard_id}")
def get_standard(standard_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        row = session.get(Standard, standard_id)
        if not row or not row.is_active:
            raise HTTPException(status_code=404, detail="Standard not found")
        checks = session.exec(
            select(StandardCheck).where(StandardCheck.standard_id == standard_id)
        ).all()
        data = _serialize_standard(row, check_count=len(checks))
        data["checks"] = [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "weight": c.weight,
                "severity": c.severity,
                "rule_field": c.rule_field,
                "rule_operator": c.rule_operator,
            }
            for c in checks
        ]
        return data


@router.post("")
def create_standard(body: StandardCreate, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        dup = session.exec(select(Standard).where(Standard.slug == body.slug.strip())).first()
        if dup:
            raise HTTPException(status_code=400, detail="Standard slug already exists")
        row = Standard(
            id=str(uuid.uuid4()),
            name=body.name.strip(),
            slug=body.slug.strip(),
            description=(body.description or "").strip(),
            version=(body.version or "1.0").strip(),
            applies_to_kind=(body.applies_to_kind or "all").strip(),
            is_active=1,
            created_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize_standard(row, check_count=0)


@catalog_router.get("/{entity_id}/standards")
def list_entity_standards(entity_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        _get_active_entity(session, entity_id)
        rows = session.exec(
            select(EntityStandardEvaluation)
            .where(EntityStandardEvaluation.entity_id == entity_id)
            .order_by(EntityStandardEvaluation.evaluated_at.desc())
        ).all()
        out = []
        for ev in rows:
            item = _serialize_evaluation(ev)
            std = session.get(Standard, ev.standard_id)
            if std:
                item["standard_name"] = std.name
                item["standard_slug"] = std.slug
            out.append(item)
        return out


@catalog_router.post("/{entity_id}/standards/{standard_id}/evaluate")
def evaluate_entity_standard(
    entity_id: str,
    standard_id: str,
    current_user: User = Depends(get_current_user),
):
    with Session(engine) as session:
        entity = _get_active_entity(session, entity_id)
        standard = session.get(Standard, standard_id)
        if not standard or not standard.is_active:
            raise HTTPException(status_code=404, detail="Standard not found")
        row = _run_evaluation(session, entity, standard)
        payload = _serialize_evaluation(row)
        payload["standard_name"] = standard.name
        payload["standard_slug"] = standard.slug
        return payload
