"""Onboarding agent — golden-path service scaffolding."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..context import PlatformContext
from .base import BaseAgent


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

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        service_name, team, template = _parse_onboarding(task, params)

        details = {
            "service_name": service_name,
            "team": team,
            "template": template,
            "steps_pending": [
                "create_github_repo",
                "apply_branch_protection",
                "create_catalog_entry",
                "scaffold_from_template",
            ],
        }

        return self._build_result(
            context,
            status="pending_approval",
            summary=f"Onboard {service_name} for team {team} ({template})",
            details=details,
            requires_approval=True,
            approval_payload={
                "actions": [
                    "create_github_repo",
                    "apply_branch_protection",
                    "create_catalog_entry",
                    "scaffold_from_template",
                ],
                "service_name": service_name,
                "team": team,
                "template_type": template,
            },
        )


onboarding_agent = OnboardingAgent()
