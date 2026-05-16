"""Catalog entity scorecards — AI evaluation and persisted checks."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Field, Session, SQLModel, select

from ..ai.ai_utils import ask_ai
from ..auth import User, get_current_user
from ..database import engine
from .catalog import CatalogEntity

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
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _get_active_entity(session: Session, entity_id: str) -> CatalogEntity:
    row = session.get(CatalogEntity, entity_id)
    if not row or not row.is_active:
        raise HTTPException(status_code=404, detail="Catalog entity not found")
    return row


def _parse_scorecard_json(text: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    data = json.loads(cleaned)
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise ValueError("checks must be a list")
    return checks


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


def _build_payload(rows: list[ScorecardCheck]) -> dict[str, Any]:
    flat: list[dict[str, Any]] = []
    for r in rows:
        flat.append(
            {
                "category": r.category,
                "check_name": r.check_name,
                "status": r.status,
                "score": r.score,
                "rationale": r.rationale or "",
            }
        )
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

    return {
        "overall_score": overall,
        "checks": flat,
        "by_category": grouped,
    }


def _rule_based_checks(entity: CatalogEntity) -> list[dict[str, Any]]:
    """Deterministic fallback when AI is unavailable or returns invalid JSON."""

    def chk(category: str, name: str, ok: bool, partial: bool, pass_r: str, warn_r: str, fail_r: str) -> dict:
        if ok:
            return {"category": category, "check_name": name, "status": "pass", "score": 95, "rationale": pass_r}
        if partial:
            return {"category": category, "check_name": name, "status": "warn", "score": 55, "rationale": warn_r}
        return {"category": category, "check_name": name, "status": "fail", "score": 25, "rationale": fail_r}

    desc = (entity.description or "").strip()
    repo = (entity.repo_url or "").strip()
    tags = (entity.tags or "").strip()
    lifecycle = (entity.lifecycle or "").lower()
    lang = (entity.language or "").strip()
    health = (entity.health_status or "unknown").lower()
    owner = (entity.owner_team or "").strip()

    return [
        chk("Documentation", "Has description", bool(desc), False, "Description is present.", "Description is missing.", "Description is missing."),
        chk("Documentation", "Has repo URL", bool(repo), False, "Repository URL is set.", "Repository URL is missing.", "Repository URL is missing."),
        chk("Reliability", "Lifecycle declared", lifecycle in ("experimental", "production", "deprecated"), False, "Lifecycle is declared.", "Lifecycle value is unusual.", "Lifecycle is not set."),
        chk("Reliability", "Health status set", health != "unknown", health == "degraded", "Health status is known.", "Health is degraded.", "Health status is unknown."),
        chk("Security", "Language declared", bool(lang), False, "Language is declared.", "Language is not declared.", "Language is not declared."),
        chk("Security", "Not in experimental", lifecycle != "experimental", False, "Not in experimental lifecycle.", "Entity is in experimental lifecycle.", "Entity is in experimental lifecycle."),
        chk("Ownership", "Owner team assigned", bool(owner), False, "Owner team is assigned.", "Owner team is missing.", "Owner team is missing."),
        chk("Ownership", "Has tags", bool(tags and tags not in ("[]", "null")), False, "Tags are present.", "Tags are missing.", "Tags are missing."),
    ]


def _persist_checks(session: Session, entity_id: str, checks: list[dict[str, Any]]) -> list[ScorecardCheck]:
    for old in session.exec(select(ScorecardCheck).where(ScorecardCheck.entity_id == entity_id)).all():
        session.delete(old)
    now = datetime.now(timezone.utc)
    rows: list[ScorecardCheck] = []
    for c in checks:
        row = ScorecardCheck(
            id=str(uuid.uuid4()),
            entity_id=entity_id,
            category=str(c.get("category", "General")),
            check_name=str(c.get("check_name", "Check")),
            status=_normalize_status(str(c.get("status", "warn"))),
            score=_clamp_score(c.get("score", 0)),
            rationale=str(c.get("rationale", ""))[:500],
            evaluated_at=now,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    return rows


def _evaluation_prompt(entity: CatalogEntity) -> str:
    return f"""You are a platform engineering scorecard engine.
Evaluate this software entity and return ONLY valid JSON, no markdown:

Entity: {entity.name}
Kind: {entity.kind}
Lifecycle: {entity.lifecycle}
Owner Team: {entity.owner_team}
Language: {entity.language or 'unknown'}
Repo URL: {entity.repo_url or 'none'}
Description: {entity.description or 'none'}
Tags: {entity.tags or 'none'}

Return exactly this JSON shape:
{{
  "checks": [
    {{"category": "Documentation", "check_name": "Has description", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Documentation", "check_name": "Has repo URL", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Reliability",   "check_name": "Lifecycle declared", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Reliability",   "check_name": "Health status set", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Security",      "check_name": "Language declared", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Security",      "check_name": "Not in experimental", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Ownership",     "check_name": "Owner team assigned", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}},
    {{"category": "Ownership",     "check_name": "Has tags", "status": "pass|warn|fail", "score": 0-100, "rationale": "one sentence"}}
  ]
}}"""


@router.get("/{entity_id}/scorecard")
def get_scorecard(entity_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        _get_active_entity(session, entity_id)
        rows = session.exec(
            select(ScorecardCheck)
            .where(ScorecardCheck.entity_id == entity_id)
            .order_by(ScorecardCheck.category, ScorecardCheck.check_name)
        ).all()
        return _build_payload(list(rows))


@router.post("/{entity_id}/scorecard/evaluate")
async def evaluate_scorecard(entity_id: str, current_user: User = Depends(get_current_user)):
    with Session(engine) as session:
        entity = _get_active_entity(session, entity_id)
        prompt = _evaluation_prompt(entity)
        checks_data: list[dict[str, Any]]
        try:
            raw = await ask_ai(prompt)
            checks_data = _parse_scorecard_json(raw)
        except Exception:
            checks_data = _rule_based_checks(entity)

        rows = _persist_checks(session, entity_id, checks_data)
        return _build_payload(rows)
