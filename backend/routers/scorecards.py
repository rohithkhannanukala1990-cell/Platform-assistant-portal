"""Catalog entity scorecards — AI evaluation and persisted checks."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Field, Session, SQLModel, select

from ..auth import User, get_current_user
from ..database import engine
from .catalog import CatalogEntity
from ..services.isolation import assert_same_tenant, require_tenant
from ..services.scorecard_evidence import (
    build_evidence_checks,
    build_evidence_checks_async,
    weighted_overall_score,
)

router = APIRouter(prefix="/api/catalog", tags=["scorecards"])

CATEGORY_ORDER = ["Documentation", "Reliability", "Security", "Ownership"]


class ScorecardCheck(SQLModel, table=True):
    __tablename__ = "scorecard_checks"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    entity_id: str = Field(foreign_key="catalog_entities.id", index=True)
    category: str
    check_name: str
    status: str
    score: int
    rationale: str = ""
    last_evidence_json: Optional[str] = Field(default="{}")
    weight: float = Field(default=0.0)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _get_active_entity(
    session: Session, entity_id: str, *, tenant_id: str | None = None
) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    if tenant_id is not None:
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
    return row


def _normalize_status(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("pass", "warn", "fail"):
        return s
    if s == "warning":
        return "warn"
    if s in ("failed", "error"):
        return "fail"
    return "warn"


def _clamp_score(val: Any) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = 0
    return max(0, min(100, n))


def _build_payload(rows: list[ScorecardCheck], *, narrative: str | None = None) -> dict[str, Any]:
    flat: list[dict[str, Any]] = []
    for r in rows:
        try:
            evidence = json.loads(getattr(r, "last_evidence_json", None) or "{}")
        except (json.JSONDecodeError, TypeError, ValueError):
            evidence = {}
        flat.append(
            {
                "category": r.category,
                "check_name": r.check_name,
                "status": r.status,
                "score": r.score,
                "rationale": r.rationale or "",
                "evidence": evidence if isinstance(evidence, dict) else {},
                "weight": float(getattr(r, "weight", 0) or 0),
            }
        )
    # Prefer weighted score when weights present; else simple average.
    if any(c.get("weight") for c in flat):
        overall = weighted_overall_score(flat)
    else:
        overall = round(sum(c["score"] for c in flat) / len(flat)) if flat else 0

    by_cat: dict[str, list[dict[str, Any]]] = {}
    for c in flat:
        by_cat.setdefault(c["category"], []).append(c)

    grouped = []
    seen = set()
    for cat in CATEGORY_ORDER:
        if cat in by_cat:
            grouped.append({"category": cat, "checks": by_cat[cat]})
            seen.add(cat)
    for cat, items in by_cat.items():
        if cat not in seen:
            grouped.append({"category": cat, "checks": items})

    payload = {
        "overall_score": overall,
        "checks": flat,
        "by_category": grouped,
        "version": "v2",
    }
    if narrative:
        payload["narrative"] = narrative
    return payload


def _rule_based_checks(entity: CatalogEntity) -> list[dict[str, Any]]:
    """Legacy deterministic checks — prefer evidence v2 via build_evidence_checks."""
    return build_evidence_checks(entity)


def _persist_checks(session: Session, entity_id: str, checks: list[dict[str, Any]]) -> list[ScorecardCheck]:
    for old in session.exec(select(ScorecardCheck).where(ScorecardCheck.entity_id == entity_id)).all():
        session.delete(old)
    now = datetime.now(timezone.utc)
    rows: list[ScorecardCheck] = []
    for c in checks:
        evidence = c.get("evidence") if isinstance(c.get("evidence"), dict) else {}
        row = ScorecardCheck(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            category=str(c.get("category", "General")),
            check_name=str(c.get("check_name", "Check")),
            status=_normalize_status(str(c.get("status", "warn"))),
            score=_clamp_score(c.get("score", 0)),
            rationale=str(c.get("rationale", ""))[:500],
            last_evidence_json=json.dumps(evidence, default=str),
            weight=float(c.get("weight") or 0),
            evaluated_at=now,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


async def evaluate_scorecard_evidence(
    entity_id: str,
    *,
    narrative: bool = False,
    tenant_id: str | None = None,
    user: User | None = None,
) -> dict[str, Any]:
    """Evidence-based evaluate. Uses live GitHub CI when connector present; else metadata."""
    with Session(engine) as session:
        entity = _get_active_entity(session, entity_id, tenant_id=tenant_id)
        github = None
        if user is not None:
            try:
                from ..services.github_access import try_github_connector_for_user

                github = try_github_connector_for_user(
                    user,
                    tenant_id=tenant_id,
                    workspace_id=getattr(user, "workspace_id", None),
                )
            except Exception:
                github = None
        checks_data = await build_evidence_checks_async(entity, github_connector=github)
        rows = _persist_checks(session, entity_id, checks_data)
        narrative_text = None
        if narrative:
            try:
                from ..agents.scorecard_agent import scorecard_agent
                from ..context import PlatformContext

                ctx = PlatformContext.from_dict(
                    {
                        "user_id": "scorecard",
                        "user_role": "Admin",
                        "tenant_id": getattr(entity, "tenant_id", None) or "default",
                        "environment": "development",
                    },
                    user_id="scorecard",
                    user_role="Admin",
                )
                result = await scorecard_agent.run(
                    {"entity_id": entity_id, "narrative": True},
                    ctx,
                    session,
                )
                narrative_text = (result.details or {}).get("narrative")
            except Exception:
                narrative_text = None
        return _build_payload(rows, narrative=narrative_text)


@router.get("/{entity_id}/scorecard")
def get_scorecard(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        _get_active_entity(session, entity_id, tenant_id=tenant_id)
        rows = session.exec(
            select(ScorecardCheck)
            .where(ScorecardCheck.entity_id == entity_id)
            .order_by(ScorecardCheck.category, ScorecardCheck.check_name)
        ).all()
        return _build_payload(list(rows))


@router.post("/{entity_id}/scorecard/evaluate")
async def evaluate_scorecard(
    request: Request,
    entity_id: str,
    current_user: User = Depends(get_current_user),
):
    """Evidence-based checks; live GitHub CI when connector present, else metadata."""
    tenant_id = require_tenant(request)
    return await evaluate_scorecard_evidence(
        entity_id, narrative=False, tenant_id=tenant_id, user=current_user
    )
