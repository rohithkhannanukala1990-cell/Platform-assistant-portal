"""Artifact write-back approvals — DB-frozen anti-TOCTOU proposals."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import Column, Text
from sqlmodel import Field, Session, SQLModel, col, select

from ..auth import User, write_audit
from ..db.core import engine
from ..db.models.ai_models import AgentRun


class ArtifactApproval(SQLModel, table=True):
    """Frozen connector write proposal — params execute from DB only."""

    __tablename__ = "artifact_approvals"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    tenant_id: str = Field(index=True)
    username: str = Field(index=True)
    agent: str = Field(default="", index=True)
    connector: str = Field(index=True)
    method: str = Field(index=True)
    params_json: str = Field(default="{}", sa_column=Column(Text))
    preview_json: str = Field(default="{}", sa_column=Column(Text))
    idempotency_key: str = Field(index=True)
    status: str = Field(default="pending", index=True)  # pending|approved|rejected|failed
    agent_run_id: Optional[str] = Field(default=None, index=True)
    result_url: Optional[str] = Field(default=None)
    result_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    grounding: str = Field(default="none")
    decided_by: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)
    approvers_json: str = Field(default="[]", sa_column=Column(Text))
    approvals_required: int = Field(default=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: Optional[datetime] = Field(default=None)


def make_artifact_idempotency_key(
    *,
    tenant_id: str,
    connector: str,
    method: str,
    params: dict[str, Any],
) -> str:
    blob = json.dumps(
        {"tenant_id": tenant_id, "connector": connector, "method": method, "params": params},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def serialize_artifact_approval(row: ArtifactApproval) -> dict[str, Any]:
    preview = {}
    params = {}
    result = None
    try:
        preview = json.loads(row.preview_json or "{}")
    except Exception:
        preview = {}
    try:
        params = json.loads(row.params_json or "{}")
    except Exception:
        params = {}
    try:
        result = json.loads(row.result_json) if row.result_json else None
    except Exception:
        result = None
    approvers: list[str] = []
    try:
        raw_appr = json.loads(getattr(row, "approvers_json", None) or "[]")
        if isinstance(raw_appr, list):
            approvers = [str(x) for x in raw_appr]
    except Exception:
        approvers = []
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "username": row.username,
        "agent": row.agent,
        "connector": row.connector,
        "method": row.method,
        "params": params,
        "preview": preview,
        "idempotency_key": row.idempotency_key,
        "status": row.status,
        "agent_run_id": row.agent_run_id,
        "result_url": row.result_url,
        "result": result,
        "grounding": row.grounding,
        "decided_by": row.decided_by,
        "error": row.error,
        "approvers": approvers,
        "approvals_required": int(getattr(row, "approvals_required", 1) or 1),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def propose_artifact(
    *,
    tenant_id: str,
    username: str,
    agent: str,
    connector: str,
    method: str,
    params: dict[str, Any],
    preview: dict[str, Any],
    grounding: str = "none",
    summary: str = "",
    environment: str = "development",
    workspace_id: str | None = None,
    approvals_required: int = 1,
) -> dict[str, Any]:
    """Freeze artifact params in DB and open a pending AgentRun for HITL."""
    safe_params = dict(params or {})
    # Never persist secrets
    for k in list(safe_params.keys()):
        lk = str(k).lower()
        if any(x in lk for x in ("token", "password", "secret", "api_key", "credential")):
            safe_params.pop(k, None)

    idem = make_artifact_idempotency_key(
        tenant_id=tenant_id,
        connector=connector,
        method=method,
        params=safe_params,
    )
    req = max(1, int(approvals_required or 1))

    with Session(engine) as session:
        existing = session.exec(
            select(ArtifactApproval).where(
                ArtifactApproval.tenant_id == tenant_id,
                ArtifactApproval.idempotency_key == idem,
                col(ArtifactApproval.status).in_(["pending", "approved"]),
            )
        ).first()
        if existing:
            return serialize_artifact_approval(existing)

        run_id = str(uuid.uuid4())
        approval_id = str(uuid.uuid4())
        approval = ArtifactApproval(
            id=approval_id,
            tenant_id=tenant_id,
            username=username,
            agent=agent,
            connector=connector,
            method=method,
            params_json=json.dumps(safe_params, default=str),
            preview_json=json.dumps(preview or {}, default=str),
            idempotency_key=idem,
            status="pending",
            agent_run_id=run_id,
            grounding=(grounding or "none"),
            approvers_json="[]",
            approvals_required=req,
        )
        run = AgentRun(
            id=run_id,
            agent=agent or "artifact_write",
            task=summary or f"Propose {connector}.{method}",
            status="pending_approval",
            summary=summary or f"Approve {connector}.{method}",
            details_json=json.dumps(
                {
                    "source": "artifact",
                    "artifact_approval_id": approval_id,
                    "connector": connector,
                    "method": method,
                    "preview": preview,
                    "grounding": grounding,
                },
                default=str,
            ),
            requires_approval=True,
            approval_payload_json=json.dumps(
                {
                    "artifact_approval_id": approval_id,
                    "connector": connector,
                    "method": method,
                    "preview": preview,
                },
                default=str,
            ),
            environment=environment or "development",
            workspace_id=workspace_id or "",
            triggered_by=username,
            tenant_id=tenant_id,
            user_id=username,
        )
        session.add(approval)
        session.add(run)
        session.commit()
        session.refresh(approval)
        out = serialize_artifact_approval(approval)

    write_audit(
        username,
        "User",
        "artifact_proposed",
        resource=f"artifact:{approval_id}",
        detail=f"{connector}.{method}",
    )
    return out


async def fulfill_artifact_approval(
    *,
    approval_id: str,
    tenant_id: str,
    decided_by: str,
    user: User,
    confirmation: str | None = None,
) -> dict[str, Any]:
    """Execute connector write using DB-frozen params only."""
    with Session(engine) as session:
        row = session.get(ArtifactApproval, approval_id)
        if not row or row.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status == "approved" and row.result_url:
            return {
                "ok": True,
                "url": row.result_url,
                "result": json.loads(row.result_json or "{}"),
                "idempotent": True,
            }
        if row.status not in {"pending", "approved"}:
            raise HTTPException(status_code=409, detail=f"Approval status is {row.status}")

        try:
            preview = json.loads(row.preview_json or "{}")
        except Exception:
            preview = {}
        try:
            params = json.loads(row.params_json or "{}")
        except Exception:
            params = {}

        # Typed confirmation for destructive terraform plans
        require_typed = bool(preview.get("require_typed_confirm")) or int(
            preview.get("destroy_count") or params.get("destroy_count") or 0
        ) > 0
        if require_typed:
            expected = str(
                preview.get("confirm_phrase")
                or params.get("workspace")
                or preview.get("workspace")
                or ""
            ).strip()
            if not expected or str(confirmation or "").strip() != expected:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Typed confirmation required: enter the exact workspace name "
                        f"'{expected}' to approve a plan that destroys resources."
                    ),
                )

        # Multi-approver gate (destructive migrations)
        required = max(1, int(getattr(row, "approvals_required", 1) or 1))
        try:
            approvers = json.loads(getattr(row, "approvers_json", None) or "[]")
            if not isinstance(approvers, list):
                approvers = []
        except Exception:
            approvers = []
        if decided_by in approvers:
            raise HTTPException(
                status_code=400,
                detail="Same user cannot approve twice — a distinct second approver is required",
            )
        approvers = [*approvers, decided_by]
        row.approvers_json = json.dumps(approvers)
        session.add(row)
        session.commit()

        if len(approvers) < required:
            # Keep pending — do not execute yet; restore agent run after claim.
            if row.agent_run_id:
                run = session.get(AgentRun, row.agent_run_id)
                if run:
                    run.status = "pending_approval"
                    run.requires_approval = True
                    session.add(run)
                    session.commit()
            session.refresh(row)
            out = serialize_artifact_approval(row)
            out["ok"] = True
            out["partial"] = True
            out["message"] = (
                f"Recorded approval {len(approvers)}/{required}. "
                "Awaiting a distinct second approver."
            )
            return out

        connector = row.connector
        method = row.method
        idem = row.idempotency_key
        session.expunge(row)

    try:
        result = await _execute_connector_write(
            connector=connector,
            method=method,
            params=params,
            idempotency_key=idem,
            user=user,
            tenant_id=tenant_id,
        )
    except Exception as exc:
        # State lock: leave approval pending so it can be retried
        from .terraform_service import TerraformStateLocked

        is_lock = isinstance(exc, TerraformStateLocked) or (
            isinstance(exc, HTTPException)
            and "state is locked" in str(getattr(exc, "detail", "")).lower()
        )
        with Session(engine) as session:
            row = session.get(ArtifactApproval, approval_id)
            if row:
                try:
                    appr = json.loads(row.approvers_json or "[]")
                    if isinstance(appr, list) and decided_by in appr:
                        # Only drop this actor for single-approver retries / lock.
                        # Keep prior approvers for multi-approver flows.
                        if is_lock or int(getattr(row, "approvals_required", 1) or 1) <= 1:
                            appr = [a for a in appr if a != decided_by]
                            row.approvers_json = json.dumps(appr)
                except Exception:
                    pass
                if is_lock:
                    holder = getattr(exc, "holder", None) or "unknown"
                    detail = (
                        str(getattr(exc, "detail", None) or exc)
                        if not isinstance(exc, TerraformStateLocked)
                        else str(exc)
                    )
                    row.status = "pending"
                    row.error = f"state_locked:{holder}: {detail}"[:1000]
                    row.decided_by = None
                    row.decided_at = None
                    row.result_url = None
                    row.result_json = None
                    session.add(row)
                    if row.agent_run_id:
                        run = session.get(AgentRun, row.agent_run_id)
                        if run:
                            run.status = "pending_approval"
                            session.add(run)
                    session.commit()
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Terraform state is locked by {holder}. "
                            "Approval left pending for retry."
                        ),
                    ) from exc
                row.status = "failed"
                row.error = str(getattr(exc, "detail", None) or exc)[:1000]
                row.decided_by = decided_by
                row.decided_at = datetime.now(timezone.utc)
                session.add(row)
                session.commit()
        raise

    url = (
        (result or {}).get("url")
        or (result or {}).get("html_url")
        or (result or {}).get("browse_url")
    )
    with Session(engine) as session:
        row = session.get(ArtifactApproval, approval_id)
        if row:
            row.status = "approved" if result.get("ok", True) else "failed"
            row.result_url = url
            row.result_json = json.dumps(result, default=str)
            row.decided_by = decided_by
            row.decided_at = datetime.now(timezone.utc)
            if not result.get("ok", True):
                row.error = str(result.get("error") or result)[:1000]
                row.status = "failed"
            session.add(row)
            session.commit()

    write_audit(
        decided_by,
        "Admin",
        "artifact_fulfilled",
        resource=f"artifact:{approval_id}",
        detail=url or json.dumps(result, default=str)[:400],
    )
    return {"ok": bool(result.get("ok", True)), "url": url, "result": result, "idempotent": False}


def reject_artifact_approval(
    *,
    approval_id: str,
    tenant_id: str,
    decided_by: str,
    reason: str = "",
) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(ArtifactApproval, approval_id)
        if not row or row.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="Not found")
        if row.status not in {"pending"}:
            raise HTTPException(status_code=409, detail=f"Approval status is {row.status}")
        row.status = "rejected"
        row.decided_by = decided_by
        row.decided_at = datetime.now(timezone.utc)
        row.error = (reason or "Rejected")[:1000]
        run_id = row.agent_run_id
        session.add(row)
        if run_id:
            run = session.get(AgentRun, run_id)
            if run and run.status == "pending_approval":
                run.status = "rejected"
                session.add(run)
        session.commit()

    write_audit(
        decided_by,
        "Admin",
        "artifact_rejected",
        resource=f"artifact:{approval_id}",
        detail=f"actor={decided_by}; reason={reason or 'Rejected'}"[:500],
    )
    return {"ok": True, "status": "rejected"}


async def _execute_connector_write(
    *,
    connector: str,
    method: str,
    params: dict[str, Any],
    idempotency_key: str,
    user: User,
    tenant_id: str,
) -> dict[str, Any]:
    from ..connectors.registry import get_connector

    account: dict[str, Any] = {"tool_id": connector}
    # Resolve scoped account when possible
    try:
        if connector == "github":
            from .github_access import try_github_connector_for_user

            conn = try_github_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="GitHub not connected")
        elif connector == "jira":
            from .jira_access import try_jira_connector_for_user

            conn = try_jira_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="Jira not connected")
        elif connector == "slack":
            from .slack_access import try_slack_connector_for_user

            conn = try_slack_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="Slack not connected")
        elif connector == "servicenow":
            from .servicenow_access import try_servicenow_connector_for_user

            conn = try_servicenow_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="ServiceNow not connected")
        elif connector == "confluence":
            from .confluence_access import try_confluence_connector_for_user

            conn = try_confluence_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="Confluence not connected")
        elif connector == "aws":
            from .aws_access import try_aws_connector_for_user

            conn = try_aws_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="AWS not connected")
        elif connector == "pagerduty":
            from .pagerduty_access import try_pagerduty_connector_for_user

            conn = try_pagerduty_connector_for_user(user, tenant_id=tenant_id)
            if conn is None:
                raise HTTPException(status_code=400, detail="PagerDuty not connected")
        elif connector in {"terraform", "sql"}:
            conn = None
        else:
            conn = get_connector(connector, account)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:300]) from exc

    call_params = dict(params)
    call_params["idempotency_key"] = idempotency_key

    # Non-connector executors (frozen plan / SQL from DB)
    if connector == "terraform" and method == "apply_plan":
        from .terraform_service import TerraformStateLocked, apply_stored_plan

        try:
            result = await apply_stored_plan(
                working_directory=str(call_params.get("working_directory") or ""),
                plan_b64=str(call_params.get("plan_b64") or ""),
                workspace=str(call_params.get("workspace") or "default"),
            )
        except TerraformStateLocked:
            raise
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        return result

    if connector == "sql" and method == "execute_migration":
        from .migration_service import execute_production_migration

        # CRITICAL: forward SQL from frozen DB params only
        result = await execute_production_migration(str(call_params.get("forward_sql") or ""))
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        return result

    if connector == "github" and method == "cost_rightsizing_pr":
        result = await _fulfill_github_pr_bundle(conn, call_params, idempotency_key)
        if not isinstance(result, dict):
            result = {"ok": True, "result": result}
        if "ok" not in result:
            result["ok"] = True
        return result

    fn = getattr(conn, method, None) if conn is not None else None
    if not callable(fn):
        raise HTTPException(status_code=400, detail=f"Unknown method {connector}.{method}")

    # Map common nested github PR bump params
    if method == "create_branch":
        result = await fn(
            call_params.get("repo", ""),
            branch_name=call_params.get("branch_name"),
            from_ref=call_params.get("from_ref") or call_params.get("base") or "main",
            idempotency_key=f"{idempotency_key}:branch",
        )
    elif method == "commit_file":
        result = await fn(
            call_params.get("repo", ""),
            path=call_params.get("path"),
            content=call_params.get("content"),
            message=call_params.get("message") or call_params.get("title") or "update",
            branch=call_params.get("branch"),
            base_sha=call_params.get("base_sha"),
            idempotency_key=f"{idempotency_key}:commit",
        )
    elif method == "create_pull_request":
        result = await fn(
            call_params.get("repo", ""),
            title=call_params.get("title"),
            body=call_params.get("body") or "",
            head=call_params.get("head") or call_params.get("branch"),
            base=call_params.get("base") or "main",
            idempotency_key=f"{idempotency_key}:pr",
        )
    elif method == "github_dependency_pr":
        # Composite: branch + commit + PR from frozen content
        result = await _fulfill_github_pr_bundle(conn, call_params, idempotency_key)
    elif method == "add_pr_review":
        result = await fn(
            call_params.get("repo", ""),
            pr_number=int(call_params.get("pr_number") or 0),
            body=call_params.get("body") or "",
            event=call_params.get("event") or "COMMENT",
            comments=call_params.get("comments"),
            idempotency_key=idempotency_key,
        )
    else:
        # Generic kwargs — filter idempotency into signature
        import inspect

        sig = inspect.signature(fn)
        has_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        kwargs = {}
        for name, val in call_params.items():
            if has_var_kw or name in sig.parameters:
                kwargs[name] = val
        if "idempotency_key" in sig.parameters or has_var_kw:
            kwargs["idempotency_key"] = idempotency_key
        # Prefer binding known positional-or-keyword params; drop unknown when no **kwargs
        if not has_var_kw:
            kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
        result = await fn(**kwargs)

    if not isinstance(result, dict):
        result = {"ok": True, "result": result}
    if "ok" not in result:
        result["ok"] = True
    if "url" not in result:
        result["url"] = result.get("html_url") or result.get("browse_url")
    return result


async def _fulfill_github_pr_bundle(conn, params: dict[str, Any], idem: str) -> dict[str, Any]:
    repo = params.get("repo") or ""
    branch = params.get("branch_name") or params.get("branch") or f"bot/{idem[:8]}"
    base = params.get("base") or "main"
    path = params.get("path") or ""
    content = params.get("content") or ""
    title = params.get("title") or f"Update {path}"
    body = params.get("body") or ""
    await conn.create_branch(
        repo, branch_name=branch, from_ref=base, idempotency_key=f"{idem}:branch"
    )
    await conn.commit_file(
        repo,
        path=path,
        content=content,
        message=title,
        branch=branch,
        base_sha=params.get("base_sha"),
        idempotency_key=f"{idem}:commit",
    )
    pr = await conn.create_pull_request(
        repo,
        title=title,
        body=body,
        head=branch,
        base=base,
        idempotency_key=f"{idem}:pr",
    )
    return {
        "ok": True,
        "url": pr.get("html_url"),
        "html_url": pr.get("html_url"),
        "number": pr.get("number"),
        "reused": pr.get("reused"),
    }
