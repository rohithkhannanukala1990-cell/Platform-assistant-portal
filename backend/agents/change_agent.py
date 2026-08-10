"""Change agent — auto-drafts ChangeRecord for production changes, submits, closes."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


class ChangeAgent(BaseAgent):
    name = "change_agent"
    description = "Draft, submit, and close change requests for production changes."
    primary_tools = ["ServiceNow", "Jira"]
    read_only = False

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        action = (params.get("action") or "draft_change_request").lower()
        if action in {"draft", "draft_change_request"}:
            return self._draft(params, context, db)
        if action in {"submit", "submit_change_request"}:
            return await self._submit(params, context)
        if action in {"close", "close_change_request"}:
            return self._close(params, context)
        if action in {"check", "check_change_approved"}:
            return await self._check(params, context)
        return self._draft(params, context, db)

    def _draft(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        from ..services.change_service import draft_change_record

        change_type = str(params.get("change_type") or "deploy").lower()
        source_run_id = params.get("source_run_id") or params.get("agent_run_id")
        source_artifact_id = params.get("source_artifact_id") or params.get("artifact_id")

        record = draft_change_record(
            tenant_id=context.tenant_id or "default",
            workspace_id=context.workspace_id or None,
            change_type=change_type,
            source_run_id=str(source_run_id) if source_run_id else None,
            source_artifact_id=str(source_artifact_id) if source_artifact_id else None,
            title=str(params.get("title") or f"{change_type} change"),
            description=str(params.get("description") or ""),
            entity_id=params.get("entity_id"),
            entity_name=params.get("entity_name"),
            root_tier=params.get("root_tier"),
            destroy_count=int(params.get("destroy_count") or 0),
            rollback_plan=str(params.get("rollback_plan") or ""),
            within_business_hours=params.get("within_business_hours"),
            recent_incident_within_days=params.get("recent_incident_within_days"),
        )

        try:
            radius = json.loads(record.blast_radius_json or "{}")
        except Exception:
            radius = {}
        return self._result(
            context,
            status="success",
            summary=(
                f"Drafted {change_type} ChangeRecord {record.id} — "
                f"risk={record.risk}, dependents={radius.get('dependent_count', 0)}"
            ),
            details={
                "change_record_id": record.id,
                "change_type": record.change_type,
                "status": record.status,
                "risk": record.risk,
                "blast_radius": radius,
                "rollback_plan": record.rollback_plan,
                "source_run_id": record.source_run_id,
                "source_artifact_id": record.source_artifact_id,
            },
            grounding="live",
            confidence=0.85,
            evidence=[
                self._evidence(
                    type="change_record",
                    title=f"ChangeRecord {record.id}",
                    source="change_agent",
                    snippet=json.dumps(radius, default=str),
                )
            ],
            recommended_actions=[
                {"title": "Submit change to ServiceNow", "risk": "low", "requires_approval": False}
            ],
        )

    async def _submit(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..auth import User
        from ..db.core import engine
        from ..services.change_service import submit_change_request
        from sqlmodel import select

        change_id = str(params.get("change_id") or params.get("change_record_id") or "")
        if not change_id:
            return self._result(context, status="failed", summary="change_id required", grounding="none", confidence=0.0)
        user: User | None = None
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == (context.user_id or ""))).first()
        if user is None:
            user = User(
                username=context.user_id or "system",
                email="",
                hashed_password="",
                role="Admin",
                tenant_id=context.tenant_id or "default",
            )
        result = await submit_change_request(
            change_id=change_id,
            tenant_id=context.tenant_id or "default",
            actor=context.user_id or "system",
            user=user,
        )
        status = "success" if result.get("ok") else "failed"
        return self._result(
            context,
            status=status,
            summary=f"Submit change {change_id}: ok={result.get('ok')}",
            details=result,
            grounding="live",
            confidence=0.75 if result.get("ok") else 0.4,
        )

    async def _check(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..auth import User
        from ..db.core import engine
        from ..services.change_service import check_change_approved
        from sqlmodel import select

        change_id = str(params.get("change_id") or "")
        if not change_id:
            return self._result(context, status="failed", summary="change_id required", grounding="none", confidence=0.0)
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == (context.user_id or ""))).first()
        result = await check_change_approved(
            change_id=change_id,
            tenant_id=context.tenant_id or "default",
            user=user or User(
                username=context.user_id or "system",
                email="",
                hashed_password="",
                role="Admin",
                tenant_id=context.tenant_id or "default",
            ),
        )
        return self._result(
            context,
            status="success",
            summary=f"Change {change_id}: status={result.get('status')}",
            details=result,
            grounding="live",
            confidence=0.8,
        )

    def _close(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..services.change_service import close_change_request

        change_id = str(params.get("change_id") or "")
        if not change_id:
            return self._result(context, status="failed", summary="change_id required", grounding="none", confidence=0.0)
        outcome = str(params.get("outcome") or "success").lower()
        implemented_at = params.get("implemented_at")
        from datetime import datetime

        impl_dt = None
        if implemented_at:
            try:
                impl_dt = datetime.fromisoformat(str(implemented_at).replace("Z", "+00:00"))
            except Exception:
                impl_dt = None
        result = close_change_request(
            change_id=change_id,
            tenant_id=context.tenant_id or "default",
            outcome=outcome,
            actor=context.user_id or "system",
            implemented_at=impl_dt,
        )
        return self._result(
            context,
            status="success" if result.get("ok") else "failed",
            summary=f"Close change {change_id}: outcome={outcome}",
            details=result,
            grounding="live",
            confidence=0.85,
        )


change_agent = ChangeAgent()
