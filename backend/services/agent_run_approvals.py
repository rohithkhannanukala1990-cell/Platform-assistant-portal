"""Agent run approve/reject — extracted from routers/agents.py so the unified
approvals inbox and the Slack receiver can call the exact same logic as the
existing ``/api/agents/{run_id}/approve|reject`` endpoints (no reimplementation).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session

from ..auth import User, write_audit
from ..database import AgentRun, engine
from ..executor.safe_executor import safe_executor
from ..services.approval_claim import claim_agent_run
from ..services.isolation import assert_same_tenant


def _run_to_dict(row: AgentRun) -> dict[str, Any]:
    return {
        "run_id": row.id,
        "agent": row.agent,
        "status": row.status,
        "summary": row.summary,
        "details": json.loads(row.details_json or "{}"),
        "requires_approval": row.requires_approval,
        "approval_payload": json.loads(row.approval_payload_json or "{}"),
        "execution_log": row.execution_log,
        "triggered_by": row.triggered_by,
        "workspace": row.workspace_id,
        "environment": row.environment,
        "timestamp": row.created_at.isoformat() if row.created_at else "",
        "task": row.task,
    }


async def approve_agent_run(
    run_id: str,
    tenant_id: str,
    current_user: User,
    confirmation: Optional[str] = None,
) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
        if row.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Run is not pending approval")

        payload = json.loads(row.approval_payload_json or "{}")
        commands = payload.get("commands") or []
        if not commands and isinstance(payload.get("agents"), list):
            for sub in payload["agents"]:
                commands.extend(sub.get("details", {}).get("commands") or [])
        env = row.environment or "development"
        run_tenant = getattr(row, "tenant_id", None)
        agent_name = row.agent

        if not claim_agent_run(session, run_id):
            raise HTTPException(status_code=409, detail="Run already claimed or not pending approval")

        details = {}
        try:
            details = json.loads(row.details_json or "{}")
        except json.JSONDecodeError:
            details = {}
        is_catalog_hitl = agent_name == "catalog_self_service" and bool(
            details.get("catalog_action_id")
        )

    exec_log = None
    final_status = "success"
    catalog_result = None

    if is_catalog_hitl:
        from .catalog_actions import fulfill_catalog_action_after_hitl

        catalog_result = await fulfill_catalog_action_after_hitl(
            details=details,
            user=current_user,
            tenant_id=run_tenant or tenant_id,
        )
        exec_log = json.dumps(catalog_result, default=str)[:4000]
        status = str(catalog_result.get("status") or "")
        if status in ("failed", "error"):
            final_status = "failed"
        elif status == "not_implemented":
            final_status = "failed"
            # Honest: approved but not executed live
            exec_log = f"[post-HITL not_implemented]\n{exec_log}"
        elif catalog_result.get("ok") is False:
            final_status = "failed"
        else:
            final_status = "success"
    elif agent_name == "terminal" or details.get("source") == "terminal":
        # Terminal executes the stored command in the WS session (anti-TOCTOU).
        # Do not shell-exec here — publish decision only.
        from .terminal_service import mark_approval_status, publish_approval_decision

        approval_id = details.get("terminal_approval_id") or (
            (payload or {}).get("terminal_approval_id")
        )
        if approval_id:
            mark_approval_status(
                str(approval_id),
                status="approved",
                decided_by=current_user.username,
            )
            publish_approval_decision(
                {
                    "type": "approval_granted",
                    "approval_id": str(approval_id),
                    "agent_run_id": run_id,
                    "decided_by": current_user.username,
                }
            )
        exec_log = "[terminal] approval granted — execution deferred to terminal session"
        final_status = "success"
    elif agent_name == "editor_pr" or details.get("source") == "editor":
        from .editor_service import fulfill_editor_pr_approval

        approval_id = details.get("editor_approval_id") or (
            (payload or {}).get("editor_approval_id")
        )
        if not approval_id:
            final_status = "failed"
            exec_log = "Missing editor_approval_id"
        else:
            try:
                pr_out = await fulfill_editor_pr_approval(
                    approval_id=str(approval_id),
                    tenant_id=run_tenant or tenant_id,
                    decided_by=current_user.username,
                    user=current_user,
                )
                exec_log = json.dumps(pr_out, default=str)[:4000]
                final_status = "success" if pr_out.get("ok") else "failed"
            except HTTPException as exc:
                exec_log = str(exc.detail)
                final_status = "failed"
    elif details.get("source") == "artifact" or (payload or {}).get("artifact_approval_id"):
        from .artifact_service import fulfill_artifact_approval

        approval_id = details.get("artifact_approval_id") or (
            (payload or {}).get("artifact_approval_id")
        )
        if not approval_id:
            final_status = "failed"
            exec_log = "Missing artifact_approval_id"
        else:
            try:
                art_out = await fulfill_artifact_approval(
                    approval_id=str(approval_id),
                    tenant_id=run_tenant or tenant_id,
                    decided_by=current_user.username,
                    user=current_user,
                    confirmation=confirmation,
                )
                exec_log = json.dumps(art_out, default=str)[:4000]
                if art_out.get("partial"):
                    final_status = "pending_approval"
                else:
                    final_status = "success" if art_out.get("ok") else "failed"
            except HTTPException as exc:
                exec_log = str(exc.detail)
                # State lock / typed-confirm leave run pending when detail says so
                detail_l = str(exc.detail or "").lower()
                if exc.status_code == 409 and "locked" in detail_l:
                    final_status = "pending_approval"
                elif exc.status_code == 400 and "confirmation" in detail_l:
                    final_status = "pending_approval"
                else:
                    final_status = "failed"
    elif commands:
        exec_ctx = {
            "role": current_user.role,
            "environment": env,
            "tool": "shell",
            "tenant_id": run_tenant,
            "approved": True,
            "approved_by": current_user.username,
        }
        # HITL: dry-run / policy preview first — deny never reaches subprocess.
        preview = await safe_executor.dry_run(commands, context=exec_ctx)
        preview_log = json.dumps(
            {"dry_run": True, "all_safe": preview.get("all_safe"), "steps": preview.get("steps")},
            default=str,
        )[:4000]
        if not preview.get("all_safe"):
            exec_log = f"[approve dry-run blocked]\n{preview_log}"
            final_status = "failed"
            write_audit(
                current_user.username,
                current_user.role,
                "agent_run_denied_policy",
                resource=agent_name,
                detail=f"{run_id}: dry-run policy deny",
            )
        else:
            out = await safe_executor.execute(
                commands,
                incident_id=0,
                approved_by=current_user.username,
                context=exec_ctx,
            )
            exec_log = f"[approve dry-run ok]\n{preview_log}\n{out.get('logs') or ''}"
            final_status = "success" if out.get("success") else "failed"

    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        row.status = final_status
        row.execution_log = exec_log
        if catalog_result is not None:
            try:
                details_out = json.loads(row.details_json or "{}")
            except json.JSONDecodeError:
                details_out = {}
            details_out["post_hitl_result"] = catalog_result
            row.details_json = json.dumps(details_out, default=str)
            if catalog_result.get("message"):
                row.summary = str(catalog_result.get("message"))[:500]
        row.requires_approval = final_status == "pending_approval"
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        result = _run_to_dict(row)

    # Don't audit as approved when still pending (partial / lock / confirm fail)
    if final_status != "pending_approval":
        write_audit(
            current_user.username,
            current_user.role,
            "agent_approved",
            resource=agent_name,
            detail=run_id,
        )
    return result


def reject_agent_run(
    run_id: str,
    tenant_id: str,
    current_user: User,
) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        assert_same_tenant(getattr(row, "tenant_id", None), tenant_id)
        if row.status != "pending_approval":
            raise HTTPException(status_code=400, detail="Run is not pending approval")
        if not claim_agent_run(session, run_id, to_status="failed"):
            raise HTTPException(status_code=409, detail="Run already claimed or not pending approval")
        row = session.get(AgentRun, run_id)
        row.summary = f"Rejected by {current_user.username}: {row.summary}"
        row.requires_approval = False
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        result = _run_to_dict(row)
        try:
            details = json.loads(row.details_json or "{}")
        except json.JSONDecodeError:
            details = {}
        if row.agent == "terminal" or details.get("source") == "terminal":
            from .terminal_service import mark_approval_status, publish_approval_decision

            approval_id = details.get("terminal_approval_id")
            if approval_id:
                mark_approval_status(
                    str(approval_id),
                    status="denied",
                    decided_by=current_user.username,
                    reason="Rejected via approvals UI",
                )
                publish_approval_decision(
                    {
                        "type": "approval_denied",
                        "approval_id": str(approval_id),
                        "agent_run_id": run_id,
                        "reason": "Rejected via approvals UI",
                        "decided_by": current_user.username,
                    }
                )
        elif details.get("source") == "artifact" or details.get("artifact_approval_id"):
            from .artifact_service import reject_artifact_approval

            approval_id = details.get("artifact_approval_id")
            if approval_id:
                reject_artifact_approval(
                    approval_id=str(approval_id),
                    tenant_id=tenant_id,
                    decided_by=current_user.username,
                    reason=f"Rejected by {current_user.username}",
                )
        write_audit(
            current_user.username,
            current_user.role,
            "agent_rejected",
            resource=row.agent,
            detail=row.id,
        )
        return result
