"""Migration agent — plans infra/DB migrations with HITL and command policy."""

from __future__ import annotations

import json

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


class MigrationAgent(BaseAgent):
    name = "migration_agent"
    description = (
        "Plans and executes infrastructure and database "
        "migrations with full HITL approval gate"
    )
    requires_approval_envs = ["production"]
    primary_tools = ["kubectl", "helm", "terraform", "flyway", "liquibase"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        service_name = (
            params.get("service_name")
            or params.get("service")
            or "unknown-service"
        )
        migration_type = params.get("migration_type") or params.get("type") or "generic"
        source = params.get("source") or ""
        target = params.get("target") or ""
        dry_run = params.get("dry_run", True)
        if isinstance(dry_run, str):
            dry_run = dry_run.lower() not in ("false", "0", "no")

        evidence: list[dict] = [
            self._evidence(
                type="migration_request",
                title=f"{migration_type}: {source} → {target}",
                source="params",
                snippet=json.dumps(
                    {
                        "service_name": service_name,
                        "migration_type": migration_type,
                        "source": source,
                        "target": target,
                        "dry_run": dry_run,
                        "environment": context.environment,
                    },
                    default=str,
                ),
            )
        ]

        # Optional k8s grounding when cluster context is available.
        k8s = await self._ground_k8s(context, db)
        grounding = "partial"
        if k8s is not None:
            try:
                pods = await k8s.list_pods(params.get("namespace") or "default")
                evidence.append(
                    self._evidence(
                        type="k8s_snapshot",
                        title="Cluster pods (pre-migration)",
                        source="kubernetes",
                        snippet=f"pod_count={len(pods)}",
                    )
                )
                grounding = "live"
            except Exception as exc:
                evidence.append(
                    self._evidence(
                        type="error",
                        title="k8s grounding failed",
                        source="kubernetes",
                        snippet=str(exc)[:300],
                    )
                )

        plan: dict = {}
        try:
            raw = await self._call_llm(
                (
                    f"Create a migration plan for service '{service_name}'. "
                    f"Type={migration_type}. Source={source}. Target={target}. "
                    "Only use EVIDENCE. Do not invent cluster state. "
                    "Return JSON with steps (list of {name,command}), "
                    "estimated_downtime, rollback_steps, risks, pre_checks."
                ),
                context,
                evidence=evidence,
            )
            plan = self._parse_llm_json(raw)
        except Exception as exc:
            plan = {
                "steps": [],
                "estimated_downtime": "unknown",
                "rollback_steps": [],
                "risks": [f"Plan generation failed: {str(exc)[:200]}"],
                "pre_checks": ["Verify backups before any migration"],
            }

        if not isinstance(plan, dict):
            plan = {"steps": [str(plan)], "risks": [], "rollback_steps": [], "pre_checks": []}

        commands: list[str] = []
        for step in plan.get("steps") or []:
            if isinstance(step, dict) and step.get("command"):
                commands.append(str(step["command"]))
            elif isinstance(step, str) and step.strip().startswith(
                ("kubectl", "helm", "terraform", "flyway", "liquibase", "psql", "aws")
            ):
                commands.append(step.strip())

        recommended = [
            {
                "title": "Take a backup / snapshot before migration",
                "risk": "high",
                "requires_approval": False,
            },
            {
                "title": "Review rollback steps",
                "risk": "medium",
                "requires_approval": False,
            },
        ]

        details = {
            **plan,
            "service_name": service_name,
            "migration_type": migration_type,
            "source": source,
            "target": target,
            "dry_run": dry_run,
        }

        # Dry-run or production: never execute — finalize with policy / HITL.
        if dry_run or self._should_require_approval(context) or context.is_production():
            return self._finalize_with_policy(
                context,
                summary=(
                    f"Migration plan for {service_name} ({source} → {target}). "
                    f"Estimated downtime: {plan.get('estimated_downtime', 'unknown')}. "
                    "Backup reminder: snapshot before execute."
                ),
                details=details,
                commands=commands,
                evidence=evidence,
                grounding=grounding,
                confidence=0.65 if grounding == "live" else 0.45,
                task=f"migrate {service_name}",
                recommended_actions=recommended,
            )

        # Non-prod + dry_run=False: still must pass command policy; never bypass.
        return self._finalize_with_policy(
            context,
            summary=f"Migration ready for {service_name} ({source} → {target})",
            details=details,
            commands=commands,
            evidence=evidence,
            grounding=grounding,
            confidence=0.6,
            task=f"migrate {service_name}",
            recommended_actions=recommended,
        )


migration_agent = MigrationAgent()
