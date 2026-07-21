"""Admin audit log API — list, export, stats."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlmodel import Session, select

from ..auth import AuditLog, User, require_admin, write_audit
from ..database import AgentRun, engine

router = APIRouter(prefix="/api/audit", tags=["audit"])

CSV_COLUMNS = [
    "id",
    "timestamp",
    "user_id",
    "role",
    "action",
    "resource_type",
    "resource_id",
    "status",
    "environment",
    "workspace_id",
    "tool_id",
    "account_id",
    "parameters",
    "result",
]


_SECRET_KEY_MARKERS = ("secret", "token", "password", "api_key", "apikey", "credential", "private_key")


def _redact_secrets(value: Any) -> Any:
    """Recursively strip values whose keys look secret-bearing."""
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if any(m in str(k).lower() for m in _SECRET_KEY_MARKERS) else _redact_secrets(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


def log_audit_event(
    user: User,
    action: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
    *,
    resource_type: str = "catalog_entity",
    status: str = "success",
) -> None:
    """Reusable audit writer: who did what, to which entity, when, with what parameters.

    `details` values are redacted for secret-looking keys before persisting.
    Timestamps are added by `write_audit` (AuditLog.timestamp).
    """
    payload: dict[str, Any] = {
        "user_id": user.username,
        "role": user.role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": entity_id,
        "status": status,
    }
    if details:
        payload["parameters"] = _redact_secrets(details)
    write_audit(
        actor=user.username,
        actor_role=user.role,
        event_type=action,
        resource=f"{resource_type}:{entity_id}",
        detail=json.dumps(payload, ensure_ascii=False, default=str),
    )


def _parse_detail(detail: str) -> dict[str, Any]:
    if not detail:
        return {}
    try:
        parsed = json.loads(detail)
        return parsed if isinstance(parsed, dict) else {"result": detail}
    except json.JSONDecodeError:
        return {"result": detail}


def audit_row_to_dict(row: AuditLog) -> dict[str, Any]:
    extra = _parse_detail(row.detail or "")
    resource = row.resource or ""
    resource_type = extra.get("resource_type") or ""
    resource_id = extra.get("resource_id") or resource
    if not resource_type and ":" in resource:
        resource_type, _, resource_id = resource.partition(":")

    return {
        "id": row.id,
        "timestamp": row.timestamp.isoformat() if row.timestamp else "",
        "user_id": extra.get("user_id") or row.actor,
        "role": extra.get("role") or row.actor_role,
        "action": extra.get("action") or row.event_type,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "status": extra.get("status") or _infer_status(row.event_type, extra),
        "environment": extra.get("environment") or "",
        "workspace_id": extra.get("workspace_id") or "",
        "tool_id": extra.get("tool_id") or "",
        "account_id": extra.get("account_id") or "",
        "parameters": extra.get("parameters"),
        "result": extra.get("result") or (row.detail if not extra else extra.get("result")),
        "event_type": row.event_type,
        "actor": row.actor,
        "actor_role": row.actor_role,
        "resource": resource,
        "detail": row.detail,
        "ip_address": row.ip_address,
    }


def _infer_status(event_type: str, extra: dict) -> str:
    if extra.get("status"):
        return str(extra["status"])
    et = (event_type or "").upper()
    if "FAIL" in et or "REJECT" in et:
        return "failed"
    if "PENDING" in et or "APPROVAL" in et:
        return "pending_approval"
    return "success"


def _apply_filters(
    q,
    *,
    user_id: Optional[str],
    tool_id: Optional[str],
    action: Optional[str],
    status: Optional[str],
    environment: Optional[str],
    from_date: Optional[str],
    to_date: Optional[str],
):
    if user_id:
        q = q.where(
            or_(
                AuditLog.actor == user_id,
                AuditLog.detail.contains(f'"user_id": "{user_id}"'),
            )
        )
    if action:
        q = q.where(
            or_(
                AuditLog.event_type.contains(action),
                AuditLog.detail.contains(action),
            )
        )
    if tool_id:
        q = q.where(AuditLog.detail.contains(tool_id))
    if status:
        q = q.where(AuditLog.detail.ilike(f"%{status}%"))
    if environment:
        q = q.where(AuditLog.detail.ilike(f"%{environment}%"))
    if from_date:
        try:
            start = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
            q = q.where(AuditLog.timestamp >= start)
        except ValueError:
            pass
    if to_date:
        try:
            end = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
            q = q.where(AuditLog.timestamp <= end)
        except ValueError:
            pass
    return q


@router.get("/")
def list_audit_logs(
    user_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    action: Optional[str] = None,
    status: Optional[str] = None,
    environment: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        q = select(AuditLog)
        q = _apply_filters(
            q,
            user_id=user_id,
            tool_id=tool_id,
            action=action,
            status=status,
            environment=environment,
            from_date=from_date,
            to_date=to_date,
        )
        total = len(session.exec(q).all())
        rows = session.exec(
            q.order_by(AuditLog.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": [audit_row_to_dict(r) for r in rows],
    }


@router.get("/export")
def export_audit_csv(
    user_id: Optional[str] = None,
    tool_id: Optional[str] = None,
    action: Optional[str] = None,
    status: Optional[str] = None,
    environment: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    _admin: User = Depends(require_admin),
):
    with Session(engine) as session:
        q = select(AuditLog)
        q = _apply_filters(
            q,
            user_id=user_id,
            tool_id=tool_id,
            action=action,
            status=status,
            environment=environment,
            from_date=from_date,
            to_date=to_date,
        )
        rows = session.exec(q.order_by(AuditLog.timestamp.desc()).limit(10000)).all()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in rows:
        d = audit_row_to_dict(row)
        writer.writerow(
            {
                "id": d["id"],
                "timestamp": d["timestamp"],
                "user_id": d["user_id"],
                "role": d["role"],
                "action": d["action"],
                "resource_type": d["resource_type"],
                "resource_id": d["resource_id"],
                "status": d["status"],
                "environment": d["environment"],
                "workspace_id": d["workspace_id"],
                "tool_id": d["tool_id"],
                "account_id": d["account_id"],
                "parameters": json.dumps(d["parameters"]) if d["parameters"] is not None else "",
                "result": json.dumps(d["result"]) if isinstance(d["result"], (dict, list)) else (d["result"] or ""),
            }
        )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


@router.get("/stats")
def audit_stats(_admin: User = Depends(require_admin)):
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        all_rows = session.exec(select(AuditLog)).all()
        total_actions = len(all_rows)
        actions_today = sum(1 for r in all_rows if r.timestamp and r.timestamp >= today_start)
        unique_users = len({r.actor for r in all_rows if r.actor})

        action_counts: dict[str, int] = {}
        user_counts: dict[str, int] = {}
        failed_actions = 0
        for r in all_rows:
            d = audit_row_to_dict(r)
            act = d["action"] or r.event_type
            action_counts[act] = action_counts.get(act, 0) + 1
            uid = d["user_id"] or r.actor
            user_counts[uid] = user_counts.get(uid, 0) + 1
            if d["status"] == "failed":
                failed_actions += 1

        top_actions = sorted(
            [{"action": k, "count": v} for k, v in action_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]
        top_users = sorted(
            [{"user_id": k, "count": v} for k, v in user_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        runs = session.exec(select(AgentRun)).all()
        approved = sum(1 for r in runs if r.status == "success" and not r.requires_approval)
        rejected = sum(1 for r in runs if r.status == "failed")
        pending = sum(1 for r in runs if r.status == "pending_approval")
        decided = approved + rejected
        approval_rate = (approved / decided) if decided else 1.0

    return {
        "total_actions": total_actions,
        "actions_today": actions_today,
        "unique_users": unique_users,
        "top_actions": top_actions,
        "top_users": top_users,
        "failed_actions": failed_actions,
        "approval_rate": round(approval_rate, 4),
        "pending_approvals": pending,
    }


@router.get("/{audit_id}")
def get_audit_log(audit_id: int, _admin: User = Depends(require_admin)):
    with Session(engine) as session:
        row = session.get(AuditLog, audit_id)
        if not row:
            raise HTTPException(status_code=404, detail="Audit log not found")
    return audit_row_to_dict(row)
