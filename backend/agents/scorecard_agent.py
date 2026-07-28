"""Scorecard agent — entity scorecard evaluation from DB (grounded)."""

from __future__ import annotations

import json

from sqlmodel import Session, select

from ..context import PlatformContext
from ..routers.catalog import CatalogEntity
from ..routers.scorecards import ScorecardCheck
from .base import AgentResult, BaseAgent


class ScorecardAgent(BaseAgent):
    name = "scorecard_agent"
    description = "Scorecard evaluation and remediation tracking."
    requires_approval_envs = []
    primary_tools = ["Scorecards DB", "Jira"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        service = params.get("service") or params.get("service_name")
        threshold = params.get("score_threshold")
        entity_id = params.get("entity_id")
        evidence: list[dict] = []

        try:
            if service and not entity_id:
                ent = db.exec(
                    select(CatalogEntity).where(CatalogEntity.name == service)
                ).first()
                entity_id = ent.id if ent else None
                if ent:
                    evidence.append(
                        self._evidence(
                            type="catalog_entity",
                            title=ent.name,
                            source="catalog_db",
                            snippet=f"entity_id={ent.id}",
                        )
                    )

            q = select(ScorecardCheck)
            if entity_id:
                q = q.where(ScorecardCheck.entity_id == entity_id)
            checks = list(db.exec(q).all())
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Failed to query scorecard checks from DB",
                details={"error": str(exc)[:300]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

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

        scorecards = []
        for c in checks:
            row = {
                "entity_id": c.entity_id,
                "category": c.category,
                "check_name": c.check_name,
                "status": c.status,
                "score": c.score,
                "rationale": c.rationale,
            }
            scorecards.append(row)
            evidence.append(
                self._evidence(
                    type="scorecard_check",
                    title=f"{c.check_name} ({c.status})",
                    source="scorecards_db",
                    snippet=json.dumps(row, default=str)[:1000],
                )
            )

        note = ""
        if not checks:
            note = " No scorecard checks found in DB (empty result is live from DB)."

        summary = (
            f"Scorecard for {service or entity_id or 'all'}: {overall}% "
            f"({len(checks)} checks).{note}"
        )

        llm_narrative = None
        if checks and params.get("narrative"):
            try:
                raw = await self._call_llm(
                    "Write a short narrative from scorecard check evidence only.",
                    context,
                    evidence=evidence,
                )
                parsed = self._parse_llm_json(raw)
                llm_narrative = parsed.get("summary") or raw[:500]
            except Exception:
                llm_narrative = None

        return self._result(
            context,
            status="success",
            summary=summary.strip(),
            details={
                "service": service,
                "entity_id": entity_id,
                "scorecards": scorecards,
                "overall_score": overall,
                "failing_checks": len(failing),
                "passing_checks": len(passing),
                "empty": len(checks) == 0,
                "narrative": llm_narrative,
            },
            evidence=evidence
            or [
                self._evidence(
                    type="db_query",
                    title="Scorecard query succeeded (empty)",
                    source="scorecards_db",
                    snippet="No check rows for filter",
                )
            ],
            grounding="live",
            confidence=0.9 if checks else 0.75,
        )


scorecard_agent = ScorecardAgent()
