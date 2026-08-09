"""Migration agent — SQL shadow validation + HITL production apply."""

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
        params = params if isinstance(params, dict) else {}
        forward_sql = (
            params.get("forward_sql")
            or params.get("sql")
            or params.get("migration_sql")
            or ""
        ).strip()
        migration_type = (params.get("migration_type") or params.get("type") or "generic").lower()

        # SQL path with shadow validation
        if forward_sql or migration_type in {"sql", "database", "db"}:
            return await self._sql_shadow_propose(params, context, db)

        return await self._legacy_command_plan(params, context, db)

    async def _sql_shadow_propose(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
        from ..services.migration_service import (
            generate_rollback_sql,
            is_destructive_sql,
            run_shadow_migration,
            shadow_url_configured,
        )

        forward_sql = (
            params.get("forward_sql")
            or params.get("sql")
            or params.get("migration_sql")
            or ""
        ).strip()
        if not forward_sql:
            # Generate a conservative placeholder from params when LLM not forced
            service = params.get("service_name") or params.get("service") or "service"
            forward_sql = (
                params.get("generated_sql")
                or f"-- migration for {service}\nSELECT 1;"
            )

        rollback_sql = (params.get("rollback_sql") or "").strip() or generate_rollback_sql(
            forward_sql
        )
        allow_destructive = bool(params.get("allow_destructive"))
        destructive = is_destructive_sql(forward_sql)

        if destructive and not allow_destructive:
            return self._result(
                context,
                status="failed",
                summary="Destructive migration rejected — set allow_destructive=true to propose",
                details={
                    "destructive": True,
                    "forward_sql": forward_sql,
                    "reason": "DROP TABLE/COLUMN, TRUNCATE, or DELETE without WHERE detected",
                },
                grounding="none",
                confidence=0.0,
            )

        if not shadow_url_configured():
            return self._no_data_result(
                context,
                "Shadow validation requires SHADOW_DATABASE_URL. "
                "Set the env var to a non-production database DSN and retry — "
                "validation will not be skipped.",
                missing_tools=["SHADOW_DATABASE_URL"],
                details={"forward_sql": forward_sql, "rollback_sql": rollback_sql},
            )

        shadow = await run_shadow_migration(forward_sql)
        if shadow.get("missing_shadow"):
            return self._no_data_result(
                context,
                "Shadow validation requires SHADOW_DATABASE_URL.",
                missing_tools=["SHADOW_DATABASE_URL"],
            )

        approvals_required = 2 if destructive else 1
        preview = {
            "type": "sql_migration",
            "forward_sql": forward_sql,
            "rollback_sql": rollback_sql,
            "reversible": bool(rollback_sql) and "MANUAL" not in rollback_sql.upper(),
            "destructive": destructive,
            "allow_destructive": allow_destructive,
            "approvals_required": approvals_required,
            "shadow_run": {
                "success": bool(shadow.get("success") or shadow.get("ok")),
                "error": shadow.get("error"),
                "duration_ms": shadow.get("duration_ms"),
                "affected_rows": shadow.get("affected_rows"),
            },
            "estimated_row_impact": shadow.get("affected_rows"),
        }
        params_frozen = {
            "forward_sql": forward_sql,
            "rollback_sql": rollback_sql,
            "destructive": destructive,
            "shadow_run": preview["shadow_run"],
        }
        return self._propose_artifact_result(
            context,
            connector="sql",
            method="execute_migration",
            params=params_frozen,
            preview=preview,
            grounding="live",
            summary=(
                f"SQL migration ready "
                f"(shadow={'ok' if preview['shadow_run']['success'] else 'FAILED'}, "
                f"destructive={destructive})"
            ),
            details={
                "shadow_run": preview["shadow_run"],
                "destructive": destructive,
                "approvals_required": approvals_required,
            },
            approvals_required=approvals_required,
        )

    async def _legacy_command_plan(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
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


migration_agent = MigrationAgent()
