"""Orchestrates intent classification, agent execution, validation, and HITL (Phase G2)."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session

from ..agents import get_agent
from ..agents.base import MAX_COMMANDS_PER_RESULT, AgentResult
from ..auth import write_audit
from ..command_validator import CommandValidator
from ..context import DEFAULT_TENANT_ID, PlatformContext
from ..database import AgentRun, Notification, engine
from ..executor.safe_executor import safe_executor
from ..rbac_core import check_user_permission
from ..ws_portal import ws_broadcast
from .intent_classifier import intent_classifier
from .result_aggregator import result_aggregator

AGENT_TIMEOUT_S = 30.0


class AgentNotFound(Exception):
    pass


def _require_tenant_id(context: PlatformContext | None) -> str:
    """Return tenant_id or raise outside test/dev; never silently invent tenants."""
    import os

    tid = (context.tenant_id if context else None) or ""
    tid = str(tid).strip()
    if tid:
        return tid
    env = (os.environ.get("ENV") or os.environ.get("ENVIRONMENT") or "").strip().lower()
    if env not in ("test", "development", "dev", ""):
        raise ValueError(
            "PlatformContext.tenant_id is None in a production agent run. "
            "Check that the request middleware sets tenant context."
        )
    return DEFAULT_TENANT_ID


def _normalize_role(role: str) -> str:
    r = (role or "User").strip()
    if r.lower() == "admin":
        return "Admin"
    return "User"


def _ensure_context(context: PlatformContext) -> PlatformContext:
    """Require identity fields; fill safe defaults for tenant/environment."""
    import os

    if not (context.user_id or "").strip():
        raise ValueError("user_id is required on PlatformContext for agent runs")
    enforce = (os.getenv("ENFORCE_WORKSPACE_ISOLATION") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if enforce and not (context.tenant_id or "").strip():
        raise ValueError("tenant_id is required on PlatformContext when ENFORCE_WORKSPACE_ISOLATION is enabled")
    if not (context.tenant_id or "").strip():
        context.tenant_id = DEFAULT_TENANT_ID
    if not (context.environment or "").strip():
        context.environment = "development"
    return context


def _redact_payload(value):
    try:
        from ..services.audit_compliance import redact_secrets

        return redact_secrets(value)
    except Exception:
        return value


def _details_for_persist(result: AgentResult) -> dict:
    """Merge evidence/grounding/policy into details for AgentRun storage."""
    details = dict(result.details or {})
    details["evidence"] = list(result.evidence or [])
    details["grounding"] = result.grounding or "none"
    details["confidence"] = result.confidence
    details["errors"] = list(result.errors or [])
    details["recommended_actions"] = list(result.recommended_actions or [])
    if result.policy:
        details["policy"] = result.policy
    # Cap commands
    if isinstance(details.get("commands"), list):
        details["commands"] = [str(c) for c in details["commands"]][:MAX_COMMANDS_PER_RESULT]
    return _redact_payload(details)


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
    _ensure_context(context)
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
            tenant_id=_require_tenant_id(context),
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
        row.details_json = json.dumps(_details_for_persist(result), default=str)
        row.requires_approval = result.requires_approval
        payload = _redact_payload(result.approval_payload or {})
        row.approval_payload_json = json.dumps(payload, default=str)
        try:
            from ..services.audit_compliance import redact_secret_text

            row.execution_log = redact_secret_text(result.execution_log or "") or None
        except Exception:
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
            details_json=json.dumps(_details_for_persist(result), default=str),
            requires_approval=result.requires_approval,
            approval_payload_json=json.dumps(
                _redact_payload(result.approval_payload or {}), default=str
            ),
            execution_log=result.execution_log,
            triggered_by=result.triggered_by or user_id,
            user_id=user_id,
            workspace_id=(context.workspace_id if context else None) or result.workspace or "",
            tenant_id=_require_tenant_id(context),
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


def _validate_commands_in_result(
    result: AgentResult, context: PlatformContext | None = None
) -> AgentResult:
    from ..agents import get_agent

    # Strip commands for read-only agents (defense in depth).
    try:
        agent = get_agent(result.agent)
        if getattr(agent, "read_only", False):
            details = dict(result.details or {})
            details["commands"] = []
            payload = dict(result.approval_payload or {})
            if "commands" in payload:
                payload["commands"] = []
            return AgentResult(
                **{
                    **result.model_dump(),
                    "details": details,
                    "approval_payload": payload or None,
                    "requires_approval": False if result.status != "pending_approval" else result.requires_approval,
                }
            )
    except Exception:
        pass

    commands: list[str] = []
    if isinstance(result.details.get("commands"), list):
        commands = [str(c) for c in result.details["commands"]]
    payload = result.approval_payload or {}
    if isinstance(payload.get("commands"), list):
        commands.extend(str(c) for c in payload["commands"])

    # Cap
    if len(commands) > MAX_COMMANDS_PER_RESULT:
        commands = commands[:MAX_COMMANDS_PER_RESULT]
        details = dict(result.details or {})
        details["commands"] = commands
        details["commands_truncated"] = True
        result = AgentResult(**{**result.model_dump(), "details": details})

    if not commands:
        return result

    check = CommandValidator.validate_with_context(
        commands,
        role=(context.user_role if context else "User"),
        environment=(context.environment if context else "development"),
        tool=(context.active_tool if context and context.active_tool else "shell"),
        tenant_id=_require_tenant_id(context),
    )
    decision = check.decision
    reasons = list(decision.reasons) if decision else list(check.violations)
    policy = decision.to_dict() if decision and hasattr(decision, "to_dict") else {
        "effect": check.effect,
        "reasons": reasons,
        "matched_rule_ids": [],
        "safe_for_auto": check.safe and not check.requires_approval,
    }

    if not check.safe:
        write_audit(
            (context.user_id if context else "system") or "system",
            (context.user_role if context else "User") or "User",
            "agent_run_denied_policy",
            resource=result.agent,
            detail="; ".join(reasons)[:500],
        )
        return AgentResult(
            **{
                **result.model_dump(),
                "status": "failed",
                "summary": "Command validation failed at orchestrator",
                "details": {
                    **result.details,
                    "commands": [],
                    "violations": check.violations,
                    "policy_effect": "deny",
                    "policy_reasons": reasons,
                },
                "requires_approval": False,
                "approval_payload": {},
                "execution_log": str(check.violations),
                "policy": policy,
                "errors": reasons,
            }
        )

    # Production mutating: never auto-allow shell without HITL even if policy allows.
    env = ((context.environment if context else "") or "").strip().lower()
    import os

    process_prod = (os.getenv("ENV") or "").strip().lower() in {"production", "prod", "dr"}
    if (env in {"production", "prod", "dr"} or process_prod) and not result.requires_approval:
        return AgentResult(
            **{
                **result.model_dump(),
                "status": "pending_approval",
                "requires_approval": True,
                "approval_payload": {
                    **(result.approval_payload or {}),
                    "commands": commands,
                    "policy_reasons": ["production_mutating_requires_approval"],
                },
                "details": {
                    **result.details,
                    "commands": commands,
                    "policy_effect": "require_approval",
                },
                "policy": policy,
            }
        )

    if check.requires_approval and not result.requires_approval:
        write_audit(
            (context.user_id if context else "system") or "system",
            (context.user_role if context else "User") or "User",
            "command_policy_approval_required",
            resource=result.agent,
            detail="; ".join(reasons)[:500],
        )
        return AgentResult(
            **{
                **result.model_dump(),
                "status": "pending_approval" if result.status == "success" else result.status,
                "requires_approval": True,
                "approval_payload": {
                    **(result.approval_payload or {}),
                    "commands": commands,
                    "policy_reasons": reasons,
                },
                "details": {
                    **result.details,
                    "commands": commands,
                    "policy_effect": "require_approval",
                    "policy_reasons": reasons,
                },
                "policy": policy,
            }
        )

    if policy and not result.policy:
        return AgentResult(**{**result.model_dump(), "policy": policy})
    return result


def _timeout_result(agent_name: str, context: PlatformContext) -> AgentResult:
    return AgentResult(
        agent=agent_name,
        status="failed",
        summary="Agent timed out after 30s",
        details={"timeout_seconds": AGENT_TIMEOUT_S},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by=context.user_id or "",
        workspace=context.workspace_id or "",
        environment=context.environment or "development",
        grounding="none",
        errors=["timeout"],
    )


def _error_result(agent_name: str, context: PlatformContext, exc: Exception) -> AgentResult:
    return AgentResult(
        agent=agent_name,
        status="failed",
        summary=f"Agent {agent_name} failed: {exc}",
        details={"error": str(exc)},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by=context.user_id or "",
        workspace=context.workspace_id or "",
        environment=context.environment or "development",
        grounding="none",
        errors=[str(exc)],
    )


class OrchestratorAgent:
    async def run(
        self,
        task: str,
        context: PlatformContext,
        db: Session,
        override_agents: Optional[list[str]] = None,
        agent_params: Optional[dict] = None,
    ) -> AgentResult:
        try:
            _ensure_context(context)
        except ValueError as exc:
            write_audit(
                "system",
                context.user_role or "User",
                "agent_run_denied_policy",
                resource="orchestrator",
                detail=str(exc),
            )
            return AgentResult(
                agent="orchestrator",
                status="failed",
                summary=str(exc),
                details={"error": str(exc)},
                timestamp=datetime.now(timezone.utc).isoformat(),
                triggered_by="",
                workspace=context.workspace_id or "",
                environment=context.environment or "development",
                grounding="none",
                errors=[str(exc)],
            )

        write_audit(
            context.user_id,
            context.user_role,
            "agent_run_started",
            resource="orchestrator",
            detail=task[:500],
        )

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
                triggered_by=context.user_id or "",
                workspace=context.workspace_id or "",
                environment=context.environment or "development",
                grounding="none",
                errors=["permission_denied"],
            )

        params = {"task": task, **classified.model_dump()}
        if isinstance(agent_params, dict):
            params.update(agent_params)

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

            result = _validate_commands_in_result(result, context)
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
            write_audit(
                context.user_id,
                context.user_role,
                "agent_run_completed",
                resource=final.agent,
                detail=f"{task[:200]} → pending_approval",
            )
            return final

        commands: list[str] = []
        if isinstance(final.details.get("commands"), list):
            commands = [str(c) for c in final.details["commands"]][:MAX_COMMANDS_PER_RESULT]

        if commands and final.status == "success":
            exec_out = await safe_executor.execute(
                commands,
                incident_id=0,
                approved_by=context.user_id or "system",
                context={
                    "role": context.user_role,
                    "environment": context.environment,
                    "tool": context.active_tool or "shell",
                    "tenant_id": context.tenant_id,
                    "approved": False,
                },
            )
            final.execution_log = exec_out.get("logs")
            if not exec_out.get("success"):
                final.status = "failed"
                final.details = {**final.details, "execution": exec_out}
                if exec_out.get("policy_effect") == "deny":
                    write_audit(
                        context.user_id,
                        context.user_role,
                        "agent_run_denied_policy",
                        resource=final.agent,
                        detail=str(exec_out.get("policy_reasons") or "")[:500],
                    )
            if final.run_id:
                _complete_run(final.run_id, final)

        write_audit(
            context.user_id,
            context.user_role,
            "agent_run_completed",
            resource=final.agent,
            detail=f"{task[:200]} → {final.status} grounding={final.grounding}",
        )
        _notify(db, f"Agent run completed: {final.agent} — {final.status}", "info")

        return final


orchestrator_agent = OrchestratorAgent()


async def run_agent_for_workflow(
    agent_name: str,
    input_payload: dict | None,
    context: PlatformContext,
) -> AgentResult:
    """Invoke a named agent for the workflow engine (no HTTP hop)."""
    from ..agents import get_agent

    try:
        _ensure_context(context)
    except ValueError as exc:
        return _error_result(agent_name, context, exc)

    params = dict(input_payload or {})
    if "task" not in params:
        params["task"] = params.get("summary") or f"workflow:{agent_name}"

    with Session(engine) as db:
        if not _user_can_run_agent(db, context, agent_name):
            # Workflow engine runs as the triggering user; Admin role is typical.
            # Allow when user_role is Admin even if RBAC rows are sparse in tests.
            if _normalize_role(context.user_role) != "Admin":
                return AgentResult(
                    agent=agent_name,
                    status="failed",
                    summary="Permission denied for agent",
                    details={"error": "permission_denied"},
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    triggered_by=context.user_id or "",
                    workspace=context.workspace_id or "",
                    environment=context.environment or "development",
                    grounding="none",
                    errors=["permission_denied"],
                )
        try:
            agent = get_agent(agent_name)
        except Exception as exc:
            return _error_result(agent_name, context, exc)

        run_id = _start_run(str(params.get("task") or ""), agent_name, context)
        try:
            result = await asyncio.wait_for(
                agent.run(params, context, db),
                timeout=AGENT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            result = _timeout_result(agent_name, context)
        except Exception as exc:
            result = _error_result(agent_name, context, exc)

        if params.get("dry_run") and result.status == "success":
            result = AgentResult(**{**result.model_dump(), "status": "dry_run"})

        result = _validate_commands_in_result(result, context)
        _complete_run(run_id, result)
        result.run_id = run_id
        return result
