"""Scorecard agent — entity scorecard evaluation results."""

from __future__ import annotations

from sqlmodel import Session, select

from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from ..routers.scorecards import ScorecardCheck
from .base import BaseAgent


class ScorecardAgent(BaseAgent):
    name = "scorecard_agent"
    description = "Scorecard evaluation and remediation tracking."
    requires_approval_envs = ["production"]
    primary_tools = ["Scorecards DB", "Jira"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        service = params.get("service") or params.get("service_name")
        threshold = params.get("score_threshold")
        entity_id = params.get("entity_id")

        try:
            if service and not entity_id:
                ent = db.exec(
                    select(CatalogEntity).where(CatalogEntity.name == service)
                ).first()
                entity_id = ent.id if ent else None

            q = select(ScorecardCheck)
            if entity_id:
                q = q.where(ScorecardCheck.entity_id == entity_id)
            checks = list(db.exec(q).all())
        except Exception:
            checks = []

        if threshold is not None:
            try:
                t = int(threshold)
                checks = [c for c in checks if c.score < t]
            except (TypeError, ValueError):
                pass

        failing = [c for c in checks if c.status in ("fail", "failed")]
        passing = [c for c in checks if c.status in ("pass", "passed", "ok")]

        overall = 0
        if checks:
            overall = round(sum(c.score for c in checks) / len(checks), 1)

        scorecards = [
            {
                "entity_id": c.entity_id,
                "category": c.category,
                "check_name": c.check_name,
                "status": c.status,
                "score": c.score,
                "rationale": c.rationale,
            }
            for c in checks
        ]

        return self._build_result(
            context,
            status="success",
            summary=f"Scorecard for {service or entity_id or 'all'}: {overall}% ({len(checks)} checks)",
            details={
                "service": service,
                "entity_id": entity_id,
                "scorecards": scorecards,
                "overall_score": overall,
                "failing_checks": len(failing),
                "passing_checks": len(passing),
            },
        )


scorecard_agent = ScorecardAgent()
