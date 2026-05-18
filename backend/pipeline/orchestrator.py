"""Orchestrates intent classification, agent execution, validation, and HITL."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session

from ..agents import get_agent
from ..agents.base import AgentResult
from ..auth import write_audit
from ..command_validator import CommandValidator
from ..context import PlatformContext
from ..database import AgentRun, Notification
from ..executor.safe_executor import safe_executor
from ..rbac_core import check_user_permission
from .intent_classifier import intent_classifier
from .result_aggregator import result_aggregator


class AgentNotFound(Exception):
    pass


def _normalize_role(role: str) -> str:
    r = (role or "User").strip()
    if r.lower() == "admin":
        return "Admin"
    return "User"


def _user_can_run_agent(session: Session, context: PlatformContext, agent_name: str) -> bool:
    role = _normalize_role(context.user_role)
    if role == "Admin":
        return True
    ok, _ = check_user_permission(
        session, context.user_id, "agents", "run", "global", context.workspace_id or ""
    )
    if ok:
        return True
    ok, _ = check_user_permission(
        session, context.user_id, "ai_assistant", "manage", "global", context.workspace_id or ""
    )
    return ok


def _persist_run(session: Session, task: str, result: AgentResult) -> str:
    row = AgentRun(
        agent=result.agent,
        status=result.status,
        summary=result.summary,
        details_json=json.dumps(result.details),
        requires_approval=result.requires_approval,
        approval_payload_json=json.dumps(result.approval_payload or {}),
        execution_log=result.execution_log,
        triggered_by=result.triggered_by,
        workspace_id=result.workspace,
        environment=result.environment,
        task=task,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.id


def _notify(session: Session, message: str, ntype: str = "info") -> None:
    session.add(
        Notification(
            message=message,
            type=ntype,
            is_read=False,
        )
    )
    session.commit()


def _validate_commands_in_result(result: AgentResult) -> AgentResult:
    commands: list[str] = []
    if isinstance(result.details.get("commands"), list):
        commands = [str(c) for c in result.details["commands"]]
    payload = result.approval_payload or {}
    if isinstance(payload.get("commands"), list):
        commands.extend(str(c) for c in payload["commands"])

    if not commands:
        return result

    check = CommandValidator.validate(commands)
    if check.safe:
        return result

    return AgentResult(
        **{
            **result.model_dump(),
            "status": "failed",
            "summary": "Command validation failed at orchestrator",
            "details": {**result.details, "violations": check.violations},
            "execution_log": str(check.violations),
        }
    )


class OrchestratorAgent:
    async def run(
        self,
        task: str,
        context: PlatformContext,
        db: Session,
        override_agents: Optional[list[str]] = None,
    ) -> AgentResult:
        classified = await intent_classifier.classify(task, context)
        agent_names = override_agents or classified.suggested_agents

        if classified.environment_hint and not override_agents:
            context.environment = classified.environment_hint

        allowed: list[str] = []
        for name in agent_names:
            if _user_can_run_agent(db, context, name):
                allowed.append(name)

        if not allowed:
            return AgentResult(
                agent="orchestrator",
                status="failed",
                summary="Permission denied for suggested agents",
                details={"suggested": agent_names, "intent": classified.intent},
                timestamp=datetime.now(timezone.utc).isoformat(),
                triggered_by=context.user_id,
                workspace=context.workspace_id,
                environment=context.environment,
            )

        params = {"task": task, **classified.model_dump()}

        async def _run_one(name: str) -> AgentResult:
            agent = get_agent(name)
            return await agent.run(params, context, db)

        import asyncio

        if len(allowed) == 1:
            final = await _run_one(allowed[0])
        else:
            results = await asyncio.gather(*[_run_one(n) for n in allowed])
            final = result_aggregator.aggregate(list(results))

        final = _validate_commands_in_result(final)

        if final.status == "pending_approval" or final.requires_approval:
            run_id = _persist_run(db, task, final)
            final.run_id = run_id
            _notify(
                db,
                f"Agent approval required: {final.summary[:120]}",
                "warning",
            )
            write_audit(
                context.user_id,
                context.user_role,
                "agent_pending_approval",
                resource=final.agent,
                detail=task[:500],
            )
            return final

        commands: list[str] = []
        if isinstance(final.details.get("commands"), list):
            commands = [str(c) for c in final.details["commands"]]

        if commands and final.status == "success":
            exec_out = await safe_executor.execute(
                commands, incident_id=0, approved_by=context.user_id or "system"
            )
            final.execution_log = exec_out.get("logs")
            if not exec_out.get("success"):
                final.status = "failed"
                final.details = {**final.details, "execution": exec_out}

        run_id = _persist_run(db, task, final)
        final.run_id = run_id

        write_audit(
            context.user_id,
            context.user_role,
            "agent_run",
            resource=final.agent,
            detail=f"{task[:200]} → {final.status}",
        )
        _notify(db, f"Agent run completed: {final.agent} — {final.status}", "info")

        return final


orchestrator_agent = OrchestratorAgent()
