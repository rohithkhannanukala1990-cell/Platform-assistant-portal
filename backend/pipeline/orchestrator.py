"""Orchestrates intent classification, agent execution, validation, and HITL."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session

from ..agents import get_agent
from ..agents.base import AgentResult
from ..auth import write_audit
from ..command_validator import CommandValidator
from ..context import PlatformContext
from ..database import AgentRun, Notification, engine
from ..executor.safe_executor import safe_executor
from ..rbac_core import check_user_permission
from ..ws_portal import ws_broadcast
from .intent_classifier import intent_classifier
from .result_aggregator import result_aggregator

AGENT_TIMEOUT_S = 30.0


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


def _start_run(task: str, agent_name: str, context: PlatformContext) -> str:
    if not (context.user_id or "").strip():
        raise ValueError("user_id is required on PlatformContext for agent runs")
    with Session(engine) as session:
        row = AgentRun(
            agent=agent_name,
            status="running",
            summary=f"Running {agent_name}",
            details_json="{}",
            requires_approval=False,
            approval_payload_json="{}",
            triggered_by=context.user_id,
            user_id=context.user_id,
            workspace_id=context.workspace_id or "",
            tenant_id=context.tenant_id or "default",
            environment=context.environment,
            task=task,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _complete_run(run_id: str, result: AgentResult) -> None:
    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            return
        row.agent = result.agent
        row.status = result.status
        row.summary = result.summary
        row.details_json = json.dumps(result.details)
        row.requires_approval = result.requires_approval
        row.approval_payload_json = json.dumps(result.approval_payload or {})
        row.execution_log = result.execution_log
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()


def _persist_run(task: str, result: AgentResult, context: PlatformContext | None = None) -> str:
    user_id = (context.user_id if context else None) or result.triggered_by
    if not (user_id or "").strip():
        raise ValueError("user_id is required to persist agent runs")
    with Session(engine) as session:
        row = AgentRun(
            agent=result.agent,
            status=result.status,
            summary=result.summary,
            details_json=json.dumps(result.details),
            requires_approval=result.requires_approval,
            approval_payload_json=json.dumps(result.approval_payload or {}),
            execution_log=result.execution_log,
            triggered_by=result.triggered_by or user_id,
            user_id=user_id,
            workspace_id=(context.workspace_id if context else None) or result.workspace or "",
            tenant_id=(context.tenant_id if context else None) or "default",
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


def _timeout_result(agent_name: str, context: PlatformContext) -> AgentResult:
    return AgentResult(
        agent=agent_name,
        status="failed",
        summary="Agent timed out after 30s",
        details={"timeout_seconds": AGENT_TIMEOUT_S},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by=context.user_id,
        workspace=context.workspace_id,
        environment=context.environment,
    )


def _error_result(agent_name: str, context: PlatformContext, exc: Exception) -> AgentResult:
    return AgentResult(
        agent=agent_name,
        status="failed",
        summary=f"Agent {agent_name} failed: {exc}",
        details={"error": str(exc)},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by=context.user_id,
        workspace=context.workspace_id,
        environment=context.environment,
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

        async def _run_with_timeout(name: str) -> AgentResult:
            run_id = _start_run(task, name, context)
            await ws_broadcast(run_id, name, "running", f"Starting {name}")

            try:
                agent = get_agent(name)
                result = await asyncio.wait_for(
                    agent.run(params, context, db),
                    timeout=AGENT_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                result = _timeout_result(name, context)
            except Exception as exc:
                result = _error_result(name, context, exc)

            result = _validate_commands_in_result(result)
            _complete_run(run_id, result)
            result.run_id = run_id

            await ws_broadcast(
                run_id,
                result.agent,
                result.status,
                result.summary,
                result.timestamp,
            )
            return result

        async def _run_isolated(name: str) -> AgentResult:
            try:
                return await _run_with_timeout(name)
            except Exception as exc:
                return _error_result(name, context, exc)

        if len(allowed) == 1:
            final = await _run_isolated(allowed[0])
        else:
            results = await asyncio.gather(*[_run_isolated(n) for n in allowed])
            final = result_aggregator.aggregate(list(results))
            agg_id = _persist_run(task, final, context)
            final.run_id = agg_id
            await ws_broadcast(
                agg_id,
                final.agent,
                final.status,
                final.summary,
                final.timestamp,
            )

        if final.status == "pending_approval" or final.requires_approval:
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
            if final.run_id:
                _complete_run(final.run_id, final)

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
