"""Onboarding agent — golden-path service scaffolding (DB-grounded)."""

from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


def _parse_onboarding(task: str, params: dict) -> tuple[str, str, str]:
    text = f"{params.get('task') or params.get('message') or task or ''}"
    service = (
        params.get("service_name")
        or _match(text, r"service[_\s-]*name[=:\s]+['\"]?([\w-]+)", r"onboard\s+([\w-]+)")
        or "new-service"
    )
    team = params.get("team") or _match(text, r"team[=:\s]+['\"]?([\w-]+)") or "platform"
    template = (
        params.get("template_type")
        or params.get("template")
        or _match(text, r"template[=:\s]+['\"]?([\w-]+)")
        or "microservice"
    )
    return service, team, template


def _match(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


class OnboardingAgent(BaseAgent):
    name = "onboarding_agent"
    description = "Team and service onboarding via golden paths."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub", "Jira", "GoldenPaths DB"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        task = str(params.get("task") or params.get("message") or "")
        service_name, team, template = _parse_onboarding(task, params)
        evidence: list[dict] = []
        matched_templates: list[dict] = []

        try:
            from ..routers.golden_paths import GoldenPathTemplate

            q = select(GoldenPathTemplate).where(
                GoldenPathTemplate.is_active == True  # noqa: E712
            )
            rows = list(db.exec(q).all())
            for row in rows:
                row_dict = {
                    "id": row.id,
                    "name": row.name,
                    "slug": row.slug,
                    "category": row.category,
                    "entity_kind": row.entity_kind,
                }
                hay = f"{row.name} {row.slug} {row.category or ''} {row.entity_kind or ''}".lower()
                if template.lower() in hay or "service" in hay or not matched_templates:
                    matched_templates.append(row_dict)
                evidence.append(
                    self._evidence(
                        type="golden_path_template",
                        title=row.name,
                        source="golden_paths_db",
                        snippet=json.dumps(row_dict, default=str),
                    )
                )
        except Exception as exc:
            evidence.append(
                self._evidence(
                    type="error",
                    title="Golden path query failed",
                    source="golden_paths_db",
                    snippet=str(exc)[:300],
                )
            )

        # Prefer template ids that match requested type
        preferred = [
            t
            for t in matched_templates
            if template.lower() in f"{t.get('name')} {t.get('slug')}".lower()
        ] or matched_templates[:3]

        details = {
            "service_name": service_name,
            "team": team,
            "template": template,
            "template_ids": [t.get("id") for t in preferred if t.get("id") is not None],
            "matched_templates": preferred[:10],
            "steps_pending": [
                "create_github_repo",
                "apply_branch_protection",
                "create_catalog_entry",
                "scaffold_from_template",
            ],
        }

        grounding = "partial" if evidence else "none"
        if not evidence:
            evidence.append(
                self._evidence(
                    type="plan",
                    title="Onboarding plan (no golden-path rows)",
                    source="platform",
                    snippet=json.dumps(details, default=str)[:1000],
                )
            )

        return self._result(
            context,
            status="pending_approval",
            summary=f"Onboard {service_name} for team {team} ({template})",
            details=details,
            requires_approval=True,
            approval_payload={
                "actions": details["steps_pending"],
                "service_name": service_name,
                "team": team,
                "template_type": template,
                "template_ids": details["template_ids"],
            },
            evidence=evidence[:40],
            grounding=grounding,
            confidence=0.7 if grounding == "partial" else 0.4,
            recommended_actions=[
                {
                    "title": "Approve golden-path onboarding",
                    "risk": "medium",
                    "requires_approval": True,
                }
            ],
        )


onboarding_agent = OnboardingAgent()
