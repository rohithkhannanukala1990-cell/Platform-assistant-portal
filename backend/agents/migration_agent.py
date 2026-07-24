"""Migration agent — plans and executes infra/DB migrations with HITL approval."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlmodel import Session

from ..ai.llm_router import llm_router
from ..executor.safe_executor import safe_executor


class MigrationAgent:
    name = "migration_agent"
    description = (
        "Plans and executes infrastructure and database "
        "migrations with full HITL approval gate"
    )
    requires_approval = True
    requires_approval_envs: list[str] = ["production"]
    primary_tools: list[str] = ["kubectl", "helm", "terraform", "flyway", "liquibase"]

    async def run(
        self,
        service_name: str,
        migration_type: str,
        source: str,
        target: str,
        dry_run: bool = True,
        tool_accounts: dict = {},
        context=None,
        db: Session = None,
    ) -> dict:
        timestamp = datetime.now(timezone.utc).isoformat()
        workspace = context.workspace_name if context else "default"
        environment = context.environment if context else "production"
        user_id = context.user_id if context else "system"

        system_prompt = llm_router.build_system_prompt({
            "workspace_name": workspace,
            "environment": environment,
            "tools": list(tool_accounts.keys()),
            "tool_statuses_line": "connected",
            "production_operating": environment == "production",
        })

        plan_prompt = (
            f"Create a step-by-step migration plan for service "
            f"'{service_name}'.\n"
            f"Migration type: {migration_type}\n"
            f"Source: {source}\n"
            f"Target: {target}\n"
            f"Environment: {environment}\n"
            f"Tool accounts available: {json.dumps(tool_accounts)}\n\n"
            f"Return a JSON object with:\n"
            f"  steps: list of migration steps with commands\n"
            f"  estimated_downtime: string\n"
            f"  rollback_steps: list of rollback commands\n"
            f"  risks: list of risk strings\n"
            f"  pre_checks: list of checks to run first"
        )

        plan_raw = await llm_router.chat(
            messages=[{"role": "user", "content": plan_prompt}],
            model=None,
            system_prompt=system_prompt,
        )

        try:
            plan = json.loads(plan_raw)
        except Exception:
            plan = {
                "steps": [plan_raw],
                "estimated_downtime": "unknown",
                "rollback_steps": [],
                "risks": ["Unable to parse structured plan"],
                "pre_checks": [],
            }

        if dry_run:
            return {
                "agent": self.name,
                "status": "dry_run",
                "summary": (
                    f"Migration plan generated for {service_name} "
                    f"({source} → {target}). "
                    f"Estimated downtime: "
                    f"{plan.get('estimated_downtime', 'unknown')}. "
                    f"Awaiting approval to execute."
                ),
                "details": plan,
                "requires_approval": True,
                "approval_payload": {
                    "service_name": service_name,
                    "migration_type": migration_type,
                    "source": source,
                    "target": target,
                    "plan": plan,
                    "tool_accounts": tool_accounts,
                },
                "execution_log": None,
                "timestamp": timestamp,
                "triggered_by": user_id,
                "workspace": workspace,
                "environment": environment,
            }

        # Production requires approval — never auto-execute
        if environment == "production":
            return {
                "agent": self.name,
                "status": "pending_approval",
                "summary": (
                    f"Migration plan ready for {service_name}. "
                    f"Production execution requires admin approval."
                ),
                "details": plan,
                "requires_approval": True,
                "approval_payload": {
                    "service_name": service_name,
                    "migration_type": migration_type,
                    "source": source,
                    "target": target,
                    "plan": plan,
                    "tool_accounts": tool_accounts,
                },
                "execution_log": None,
                "timestamp": timestamp,
                "triggered_by": user_id,
                "workspace": workspace,
                "environment": environment,
            }

        # Non-production: execute via safe_executor
        commands = [
            s.get("command", s) if isinstance(s, dict) else s
            for s in plan.get("steps", [])
            if isinstance(s, (dict, str))
        ]
        result = await safe_executor.execute(
            commands=commands,
            incident_id=f"migration-{service_name}-{timestamp}",
            approved_by=user_id,
        )

        return {
            "agent": self.name,
            "status": "success" if result.get("success") else "failed",
            "summary": (
                f"Migration executed for {service_name} "
                f"({source} → {target}) in {environment}."
            ),
            "details": {**plan, "execution_result": result},
            "requires_approval": False,
            "approval_payload": None,
            "execution_log": result.get("log"),
            "timestamp": timestamp,
            "triggered_by": user_id,
            "workspace": workspace,
            "environment": environment,
        }


migration_agent = MigrationAgent()
