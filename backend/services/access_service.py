"""Access provisioning service — resource-owner routing, expiry, connector dispatch."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..auth import User, write_audit
from ..db.core import engine
from ..db.models.access import AccessRequestRecord, ResourceOwner

# Resource type → (connector, provision_method, revoke_method)
RESOURCE_TYPE_MAP: dict[str, dict[str, str]] = {
    "okta_group": {
        "connector": "okta",
        "provision": "add_user_to_group",
        "revoke": "remove_user_from_group",
    },
    "github_team": {
        "connector": "github",
        "provision": "add_team_membership",
        "revoke": "remove_team_membership",
    },
    "aws_iam_role": {
        "connector": "aws",
        "provision": "assign_iam_role",
        "revoke": "unassign_iam_role",
    },
    "k8s_role": {
        "connector": "kubernetes",
        "provision": "grant_rolebinding",
        "revoke": "revoke_rolebinding",
    },
    "jira_project": {
        "connector": "jira",
        "provision": "add_project_role",
        "revoke": "remove_project_role",
    },
}


def route_owner(
    tenant_id: str, resource_type: str, resource_id: str
) -> tuple[str, bool]:
    """Return (owner_username, owner_missing) — falls back to admin, flags missing."""
    with Session(engine) as session:
        row = session.exec(
            select(ResourceOwner).where(
                ResourceOwner.tenant_id == tenant_id,
                ResourceOwner.resource_type == resource_type,
                ResourceOwner.resource_id == resource_id,
            )
        ).first()
        if row and row.owner_username:
            return row.owner_username, False
    return "admin", True


def upsert_resource_owner(
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    owner_username: str,
    resource_name: str = "",
) -> ResourceOwner:
    with Session(engine) as session:
        row = session.exec(
            select(ResourceOwner).where(
                ResourceOwner.tenant_id == tenant_id,
                ResourceOwner.resource_type == resource_type,
                ResourceOwner.resource_id == resource_id,
            )
        ).first()
        if row:
            row.owner_username = owner_username
            if resource_name:
                row.resource_name = resource_name
            session.add(row)
        else:
            row = ResourceOwner(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                owner_username=owner_username,
            )
            session.add(row)
        session.commit()
        session.refresh(row)
        return row


def create_access_request(
    *,
    tenant_id: str,
    workspace_id: str | None,
    requester: str,
    subject: str,
    resource_type: str,
    resource_id: str,
    resource_name: str = "",
    justification: str = "",
    duration_hours: int | None = None,
    policy_assessment: dict | None = None,
) -> AccessRequestRecord:
    owner, missing = route_owner(tenant_id, resource_type, resource_id)
    mapping = RESOURCE_TYPE_MAP.get(resource_type) or {}
    connector = mapping.get("connector")
    method = mapping.get("provision")

    with Session(engine) as session:
        row = AccessRequestRecord(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            requester_username=requester,
            subject_username=subject or requester,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name or resource_id,
            justification=justification or "",
            duration_hours=int(duration_hours) if duration_hours else None,
            status="pending_approval",
            owner_username=owner,
            owner_missing=missing,
            policy_assessment_json=json.dumps(policy_assessment or {}, default=str),
            connector=connector,
            connector_method=method,
            connector_params_json=json.dumps(
                {
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "subject_username": subject or requester,
                },
                default=str,
            ),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        write_audit(
            requester,
            "User",
            "access_request_created",
            resource=f"access:{row.id}",
            detail=(
                f"resource={resource_type}:{resource_id} subject={row.subject_username} "
                f"owner={owner} owner_missing={missing}"
            ),
        )
        return row


async def provision_access_request(
    *,
    request_id: str,
    tenant_id: str,
    approver: str,
    user: User,
    connector_call=None,
) -> dict[str, Any]:
    """Approve + call the connector write method + set expires_at."""
    from .artifact_service import _execute_connector_write  # reuse scoped dispatch

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = session.get(AccessRequestRecord, request_id)
        if not row or row.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if row.status == "provisioned":
            return {
                "ok": True,
                "idempotent": True,
                "request_id": request_id,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            }
        if row.status not in {"pending_approval", "approved"}:
            return {"ok": False, "error": f"status={row.status}"}
        row.status = "approved"
        row.approved_by = approver
        row.approved_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        connector = row.connector
        method = row.connector_method
        params = json.loads(row.connector_params_json or "{}")
        session.expunge(row)

    if not connector or not method:
        with Session(engine) as session:
            r = session.get(AccessRequestRecord, request_id)
            if r:
                r.status = "provisioned"
                r.provisioned_at = now
                if r.duration_hours:
                    r.expires_at = now + timedelta(hours=int(r.duration_hours))
                session.add(r)
                session.commit()
        return {
            "ok": True,
            "request_id": request_id,
            "provisioned_at": now.isoformat(),
            "note": "no connector mapped — logical grant only",
        }

    idem = f"access:{request_id}"
    caller = connector_call
    try:
        if caller is not None:
            result = await caller(
                connector=connector, method=method, params=params, idempotency_key=idem
            )
        else:
            result = await _execute_connector_write(
                connector=connector,
                method=method,
                params=_map_params_for_connector(connector, method, params, user_email=None),
                idempotency_key=idem,
                user=user,
                tenant_id=tenant_id,
            )
    except Exception as exc:
        with Session(engine) as session:
            r = session.get(AccessRequestRecord, request_id)
            if r:
                r.status = "pending_approval"
                session.add(r)
                session.commit()
        return {"ok": False, "error": str(exc)[:400]}

    with Session(engine) as session:
        r = session.get(AccessRequestRecord, request_id)
        if r:
            r.status = "provisioned" if (result or {}).get("ok", True) else "pending_approval"
            r.provisioned_at = now if r.status == "provisioned" else None
            if r.status == "provisioned" and r.duration_hours:
                r.expires_at = now + timedelta(hours=int(r.duration_hours))
            session.add(r)
            session.commit()

    write_audit(
        approver,
        "Admin",
        "access_provisioned",
        resource=f"access:{request_id}",
        detail=f"{connector}.{method} ok={result.get('ok')}",
    )
    return {"ok": bool((result or {}).get("ok", True)), "request_id": request_id, "result": result}


def reject_access_request(
    *,
    request_id: str,
    tenant_id: str,
    decided_by: str,
    reason: str = "",
) -> dict[str, Any]:
    with Session(engine) as session:
        row = session.get(AccessRequestRecord, request_id)
        if not row or row.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if row.status != "pending_approval":
            return {"ok": False, "error": f"status={row.status}"}
        row.status = "rejected"
        row.approved_by = decided_by
        row.approved_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()

    write_audit(
        decided_by,
        "Admin",
        "access_rejected",
        resource=f"access:{request_id}",
        detail=(reason or "Rejected")[:500],
    )
    return {"ok": True, "status": "rejected"}


def _map_params_for_connector(
    connector: str, method: str, params: dict, *, user_email: str | None
) -> dict:
    p = dict(params or {})
    subject = p.get("subject_username") or user_email or ""
    resource_id = p.get("resource_id") or ""
    if connector == "okta" and method in {"add_user_to_group", "remove_user_from_group"}:
        return {"user_id": subject, "group_id": resource_id}
    if connector == "okta" and method == "deactivate_user":
        return {"user_id": subject}
    return p


async def revoke_access_request(
    *,
    request_id: str,
    tenant_id: str,
    actor: str,
    user: User,
    reason: str = "expired",
    connector_call=None,
) -> dict[str, Any]:
    """Revocation path — used by expiry sweep and manual offboarding."""
    from .artifact_service import _execute_connector_write

    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = session.get(AccessRequestRecord, request_id)
        if not row or row.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if row.status not in {"provisioned"}:
            return {"ok": True, "idempotent": True, "status": row.status}
        connector = row.connector
        mapping = RESOURCE_TYPE_MAP.get(row.resource_type) or {}
        method = mapping.get("revoke")
        params = json.loads(row.connector_params_json or "{}")

    idem = f"access-revoke:{request_id}"
    if connector and method:
        try:
            if connector_call is not None:
                result = await connector_call(
                    connector=connector, method=method, params=params, idempotency_key=idem
                )
            else:
                result = await _execute_connector_write(
                    connector=connector,
                    method=method,
                    params=_map_params_for_connector(connector, method, params, user_email=None),
                    idempotency_key=idem,
                    user=user,
                    tenant_id=tenant_id,
                )
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:400]}
    else:
        result = {"ok": True, "note": "no connector mapped"}

    with Session(engine) as session:
        r = session.get(AccessRequestRecord, request_id)
        if r:
            r.status = "expired" if reason == "expired" else "revoked"
            r.revoked_at = now
            r.revoked_by = actor
            session.add(r)
            session.commit()

    write_audit(
        actor,
        "System" if actor == "system" else "Admin",
        "access_revoked",
        resource=f"access:{request_id}",
        detail=f"reason={reason} result_ok={result.get('ok')}",
    )
    return {"ok": bool(result.get("ok", True)), "request_id": request_id, "reason": reason}


def _system_user() -> User:
    with Session(engine) as session:
        row = session.exec(select(User).where(User.username == "admin")).first()
        if row:
            return row
    return User(username="system", email="", hashed_password="", role="Admin", tenant_id="default")


async def run_expiry_sweep(*, now: Optional[datetime] = None) -> dict[str, Any]:
    """Revoke provisioned grants past expires_at; fire warning 1h before expiry."""
    from ..db.repositories.notifications import create_notification

    ts = now or datetime.now(timezone.utc)
    warn_cutoff = ts + timedelta(hours=1)
    revoked = 0
    warned = 0
    with Session(engine) as session:
        expiring = session.exec(
            select(AccessRequestRecord).where(
                AccessRequestRecord.status == "provisioned",
                col(AccessRequestRecord.expires_at).is_not(None),
                AccessRequestRecord.expires_at <= ts,
            )
        ).all()
        to_warn = session.exec(
            select(AccessRequestRecord).where(
                AccessRequestRecord.status == "provisioned",
                col(AccessRequestRecord.expires_at).is_not(None),
                AccessRequestRecord.expires_at <= warn_cutoff,
                AccessRequestRecord.expires_at > ts,
                col(AccessRequestRecord.warning_sent_at).is_(None),
            )
        ).all()

    sys_user = _system_user()
    for row in expiring:
        try:
            await revoke_access_request(
                request_id=row.id,
                tenant_id=row.tenant_id,
                actor="system",
                user=sys_user,
                reason="expired",
            )
            revoked += 1
        except Exception:
            continue
        try:
            create_notification(
                f"[Access] Grant to {row.resource_name or row.resource_id} for "
                f"{row.subject_username} expired and was revoked.",
                type="warning",
            )
        except Exception:
            pass

    with Session(engine) as session:
        for row in to_warn:
            live = session.get(AccessRequestRecord, row.id)
            if live and live.warning_sent_at is None:
                live.warning_sent_at = ts
                session.add(live)
        session.commit()
    for row in to_warn:
        try:
            create_notification(
                f"[Access] Grant to {row.resource_name or row.resource_id} for "
                f"{row.subject_username} expires at {row.expires_at.isoformat()} — "
                "request an extension if still needed.",
                type="warning",
            )
            warned += 1
        except Exception:
            continue

    return {"ok": True, "revoked": revoked, "warned": warned, "ts": ts.isoformat()}
