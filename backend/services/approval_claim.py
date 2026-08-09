"""Atomic claim helpers for HITL approval races (Phase P1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import update
from sqlmodel import Session

from ..db.models.ai_models import AIToolExecution, AgentRun
from ..db.models.mcp_models import MCPToolCall
from ..db.models.ops import Incident
from ..db.models.workflows import WorkflowRun


def _won(result: Any) -> bool:
    return bool(getattr(result, "rowcount", None) or 0)


def claim_agent_run(
    session: Session,
    run_id: str,
    *,
    from_status: str = "pending_approval",
    to_status: str = "executing",
) -> bool:
    now = datetime.now(timezone.utc)
    result = session.execute(
        update(AgentRun)
        .where(AgentRun.id == run_id, AgentRun.status == from_status)
        .values(status=to_status, updated_at=now, requires_approval=False)
    )
    session.commit()
    return _won(result)


def claim_incident_approval(
    session: Session,
    incident_id: int,
    *,
    from_status: str = "AWAITING_APPROVAL",
    to_status: str = "EXECUTING",
) -> bool:
    result = session.execute(
        update(Incident)
        .where(Incident.id == incident_id, Incident.status == from_status)
        .values(status=to_status)
    )
    session.commit()
    return _won(result)


def claim_mcp_call(
    session: Session,
    call_id: str,
    *,
    from_status: str = "pending_approval",
    to_status: str = "executing",
    approved_by: Optional[str] = None,
) -> bool:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {"status": to_status, "approved_at": now}
    if approved_by is not None:
        values["approved_by"] = approved_by
    result = session.execute(
        update(MCPToolCall)
        .where(MCPToolCall.id == call_id, MCPToolCall.status == from_status)
        .values(**values)
    )
    session.commit()
    return _won(result)


def claim_ai_execution(
    session: Session,
    execution_id: str,
    *,
    from_status: str = "pending_approval",
    to_status: str = "executing",
    approved_by: Optional[str] = None,
) -> bool:
    now = datetime.now(timezone.utc)
    values: dict[str, Any] = {"status": to_status, "approved_at": now}
    if approved_by is not None:
        values["approved_by"] = approved_by
    result = session.execute(
        update(AIToolExecution)
        .where(AIToolExecution.id == execution_id, AIToolExecution.status == from_status)
        .values(**values)
    )
    session.commit()
    return _won(result)


def claim_workflow_run(
    session: Session,
    run_id: str,
    *,
    from_status: str = "pending_approval",
    to_status: str = "running",
) -> bool:
    """CAS: exactly one concurrent approve wins (rowcount == 1)."""
    result = session.execute(
        update(WorkflowRun)
        .where(WorkflowRun.id == run_id, WorkflowRun.status == from_status)
        .values(status=to_status)
    )
    session.commit()
    return _won(result)
