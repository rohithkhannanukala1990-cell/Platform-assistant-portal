"""Catalog health agent — entity metadata completeness from DB (grounded)."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from .base import AgentResult, BaseAgent


def _score_entity(entity: CatalogEntity) -> tuple[int, dict]:
    checks = {
        "has_owner": bool((entity.owner_team or "").strip()),
        "has_docs": bool((entity.description or "").strip()),
        "has_repo": bool((entity.repo_url or "").strip()),
        "has_tags": bool(_parse_tags(entity.tags)),
    }
    score = int(sum(checks.values()) / len(checks) * 100)
    return score, checks


def _parse_tags(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [raw]
    except json.JSONDecodeError:
        return [t.strip() for t in raw.split(",") if t.strip()]


class CatalogHealthAgent(BaseAgent):
    name = "catalog_health_agent"
    description = "Catalog entity health and metadata quality checks."
    requires_approval_envs = []
    primary_tools = ["Catalog DB"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        evidence: list[dict] = []
        try:
            entities = list(
                db.exec(select(CatalogEntity).where(CatalogEntity.is_active == 1)).all()
            )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Catalog DB query failed",
                details={"error": str(exc)[:300]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        scored = []
        missing_owners = []
        missing_docs = []
        total_score = 0

        for ent in entities:
            score, checks = _score_entity(ent)
            total_score += score
            row = {
                "id": ent.id,
                "name": ent.name,
                "completeness_score": score,
                **checks,
            }
            scored.append(row)
            evidence.append(
                self._evidence(
                    type="catalog_entity",
                    title=ent.name,
                    source="catalog_db",
                    snippet=json.dumps(row, default=str)[:1000],
                )
            )
            if not checks["has_owner"]:
                missing_owners.append(ent.name)
            if not checks["has_docs"]:
                missing_docs.append(ent.name)

        complete = sum(1 for s in scored if s["completeness_score"] >= 100)
        incomplete = len(scored) - complete
        avg_score = round(total_score / len(scored), 1) if scored else 0.0

        if not evidence:
            evidence.append(
                self._evidence(
                    type="db_query",
                    title="Catalog query succeeded (empty)",
                    source="catalog_db",
                    snippet="No active catalog entities",
                )
            )

        return self._result(
            context,
            status="success",
            summary=f"Catalog health: {avg_score}% avg completeness ({len(scored)} entities)",
            details={
                "total_entities": len(scored),
                "complete": complete,
                "incomplete": incomplete,
                "avg_score": avg_score,
                "missing_owners": missing_owners[:20],
                "missing_docs": missing_docs[:20],
                "entities": scored[:50],
                "empty": len(scored) == 0,
            },
            evidence=evidence[:80],
            grounding="live",
            confidence=0.9,
        )


catalog_health_agent = CatalogHealthAgent()
