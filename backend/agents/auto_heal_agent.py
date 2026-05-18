"""Auto-heal agent — wraps backend/auto_heal.py AutoHealer."""

from __future__ import annotations

from sqlmodel import Session

from ..auto_heal import AutoHealer
from ..context import PlatformContext
from .base import BaseAgent


class AutoHealAgent(BaseAgent):
    name = "auto_heal_agent"
    description = "Low-risk automated healing for stale sessions, cache, and DB maintenance."
    requires_approval_envs = ["production"]
    primary_tools = ["Kubernetes", "ArgoCD"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        service_name = params.get("service_name") or "platform"
        issue_type = params.get("issue_type") or "general"
        namespace = params.get("namespace") or "default"

        if self._should_require_approval(context):
            return self._build_result(
                context,
                status="pending_approval",
                summary=f"Auto-heal plan for {service_name} ({issue_type}) in {namespace}",
                details={"service_name": service_name, "issue_type": issue_type, "namespace": namespace},
                requires_approval=True,
                approval_payload={"action": "auto_heal", "params": params},
            )

        healer = AutoHealer()
        healed = await healer.heal_all_low_risk()
        return self._build_result(
            context,
            status="success",
            summary=f"Auto-heal completed for {service_name}",
            details={"healed_actions": healed, "issue_type": issue_type},
            execution_log=str(healed),
        )


auto_heal_agent = AutoHealAgent()
