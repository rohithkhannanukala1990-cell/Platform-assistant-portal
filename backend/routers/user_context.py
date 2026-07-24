"""User environment/account context, pins, and access requests."""

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import User, get_current_user, require_admin, write_audit
from ..database import engine as db_engine
from ..database import AccessRequest, ToolAccount, UserAccountAccess, UserContext
from .tools import _account_to_dict, _norm_env_key

router = APIRouter(tags=["user-context"])


def _context_user_key(user: User) -> str:
    """Stable primary key for UserContext rows — always authenticated user id."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if getattr(user, "id", None) is None:
        raise HTTPException(status_code=400, detail="Authenticated user id is required")
    return str(user.id)


def _ensure_user_context_row(session: Session, user: User) -> UserContext:
    uid = _context_user_key(user)
    row = session.get(UserContext, uid)
    if row:
        return row
    # Migrate legacy demo row keyed as "admin" for the admin user only
    if getattr(user, "username", None) == "admin":
        legacy = session.get(UserContext, "admin")
        if legacy is not None and legacy.user_id != uid:
            env = legacy.active_environment
            accounts = legacy.active_accounts
            pinned = legacy.pinned_accounts
            switched = legacy.last_switched_at
            session.delete(legacy)
            session.commit()
            row = UserContext(
                user_id=uid,
                active_environment=env,
                active_accounts=accounts,
                pinned_accounts=pinned,
                last_switched_at=switched,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
    row = UserContext(
        user_id=uid,
        active_environment="development",
        active_accounts="{}",
        pinned_accounts="[]",
        last_switched_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _hydrate_active_accounts(session: Session, raw_json: str) -> dict:
    try:
        m = json.loads(raw_json or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        m = {}
    if not isinstance(m, dict):
        return {}
    out: dict = {}
    for tool_id, acc_id in m.items():
        if not isinstance(tool_id, str) or not isinstance(acc_id, str):
            continue
        acc = session.get(ToolAccount, acc_id)
        if acc and acc.tool_id == tool_id and acc.is_active == 1:
            out[tool_id] = _account_to_dict(session, acc)
    return out


def _context_payload(session: Session, row: UserContext) -> dict:
    try:
        pinned = json.loads(row.pinned_accounts or "[]")
    except (json.JSONDecodeError, TypeError, ValueError):
        pinned = []
    if not isinstance(pinned, list):
        pinned = []
    clean_pins = [p for p in pinned if isinstance(p, str)]
    return {
        "user_id": row.user_id,
        "active_environment": row.active_environment or "development",
        "active_accounts": _hydrate_active_accounts(session, row.active_accounts),
        "pinned_accounts": clean_pins,
        "last_switched_at": row.last_switched_at.isoformat() if row.last_switched_at else None,
    }


def _validate_and_dump_active_accounts(session: Session, data: dict[str, str]) -> str:
    cleaned: dict[str, str] = {}
    for tool_id, aid in data.items():
        if not isinstance(tool_id, str) or not isinstance(aid, str):
            continue
        acc = session.get(ToolAccount, aid)
        if not acc or acc.tool_id != tool_id or acc.is_active != 1:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid or inactive account for tool {tool_id}: {aid}",
            )
        cleaned[tool_id] = aid
    return json.dumps(cleaned)


def _access_request_to_dict(session: Session, r: AccessRequest) -> dict:
    acc = session.get(ToolAccount, r.account_id)
    user = None
    raw_uid = r.user_id
    if raw_uid is not None and str(raw_uid).isdigit():
        user = session.get(User, int(raw_uid))
    if user is None:
        user = session.exec(select(User).where(User.username == str(raw_uid))).first()
    return {
        "id": r.id,
        "user_id": r.user_id,
        "account_id": r.account_id,
        "reason": r.reason,
        "status": r.status,
        "reviewed_by": r.reviewed_by,
        "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        "created_at": r.created_at.isoformat(),
        "account": _account_to_dict(session, acc) if acc else None,
        "user": (
            {
                "username": user.username,
                "email": user.email,
                "role": user.role,
            }
            if user
            else {"username": r.user_id, "email": None, "role": None}
        ),
    }


class ContextUpdateBody(BaseModel):
    active_environment: str | None = None
    active_accounts: dict[str, str] | None = None
    pinned_accounts: list[str] | None = None


class ContextPinBody(BaseModel):
    account_id: str
    pinned: bool


class AccessRequestCreateBody(BaseModel):
    account_id: str
    reason: str


class AccessRequestReviewBody(BaseModel):
    status: Literal["approved", "denied"]


@router.get("/api/context")
def api_context_get(current_user: User = Depends(get_current_user)):
    with Session(db_engine) as session:
        row = _ensure_user_context_row(session, current_user)
        return _context_payload(session, row)


@router.get("/api/context/users/{user_id}")
def api_context_get_user(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Explicit admin-only read of another user's context. Non-owners get 404."""
    own = _context_user_key(current_user)
    target = str(user_id or "").strip()
    if target != own:
        role = (current_user.role or "").strip().lower()
        if role not in {"admin", "superadmin", "platformadmin"}:
            raise HTTPException(status_code=404, detail="Not found")
    with Session(db_engine) as session:
        row = session.get(UserContext, target)
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return _context_payload(session, row)


@router.put("/api/context")
async def api_context_put(
    body: ContextUpdateBody,
    current_user: User = Depends(get_current_user),
):
    from ..ws_portal import broadcast_json

    with Session(db_engine) as session:
        row = _ensure_user_context_row(session, current_user)
        if body.active_environment is not None:
            row.active_environment = _norm_env_key(body.active_environment) or "development"
        if body.active_accounts is not None:
            row.active_accounts = _validate_and_dump_active_accounts(session, body.active_accounts)
        if body.pinned_accounts is not None:
            pins = [x for x in body.pinned_accounts if isinstance(x, str)]
            row.pinned_accounts = json.dumps(pins)
        row.last_switched_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        payload = _context_payload(session, row)
    await broadcast_json(
        {
            "type": "context-changed",
            "user_id": _context_user_key(current_user),
            "context": payload,
        }
    )
    return payload


@router.post("/api/context/pin")
async def api_context_pin(
    body: ContextPinBody,
    current_user: User = Depends(get_current_user),
):
    from ..ws_portal import broadcast_json

    aid = (body.account_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="account_id is required")
    with Session(db_engine) as session:
        row = _ensure_user_context_row(session, current_user)
        try:
            pins = json.loads(row.pinned_accounts or "[]")
        except (json.JSONDecodeError, TypeError, ValueError):
            pins = []
        if not isinstance(pins, list):
            pins = []
        pins = [p for p in pins if isinstance(p, str)]
        if body.pinned:
            if aid not in pins:
                pins.append(aid)
        else:
            pins = [p for p in pins if p != aid]
        row.pinned_accounts = json.dumps(pins)
        row.last_switched_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        full = _context_payload(session, row)
    await broadcast_json(
        {
            "type": "context-changed",
            "user_id": _context_user_key(current_user),
            "context": full,
        }
    )
    return {"pinned_accounts": full["pinned_accounts"]}


@router.post("/api/access-requests")
async def api_access_requests_create(
    body: AccessRequestCreateBody,
    current_user: User = Depends(get_current_user),
):
    from ..ws_portal import broadcast_json

    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason is required")
    acc_id = (body.account_id or "").strip()
    if not acc_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    rid = str(uuid.uuid4())
    uid = _context_user_key(current_user)
    with Session(db_engine) as session:
        acc = session.get(ToolAccount, acc_id)
        if not acc or acc.is_active != 1:
            raise HTTPException(status_code=404, detail="Account not found")
        row = AccessRequest(
            id=rid,
            user_id=uid,
            account_id=acc_id,
            reason=reason,
            status="pending",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        out = _access_request_to_dict(session, row)
    await broadcast_json(
        {
            "type": "access_request_created",
            "request_id": rid,
            "user_id": uid,
            "account_id": acc_id,
        }
    )
    return out


@router.get("/api/access-requests")
def api_access_requests_list(current_user: User = Depends(require_admin)):
    with Session(db_engine) as session:
        rows = session.exec(
            select(AccessRequest)
            .where(AccessRequest.status == "pending")
            .order_by(AccessRequest.created_at.desc())
        ).all()
        return [_access_request_to_dict(session, r) for r in rows]


@router.put("/api/access-requests/{request_id}")
async def api_access_requests_review(
    request_id: str,
    body: AccessRequestReviewBody,
    request: Request,
    current_user: User = Depends(require_admin),
):
    from ..ws_portal import broadcast_json

    admin = current_user
    with Session(db_engine) as session:
        row = session.get(AccessRequest, request_id)
        if not row:
            raise HTTPException(status_code=404, detail="Request not found")
        if row.status != "pending":
            raise HTTPException(status_code=400, detail="Request is not pending")
        st = body.status.lower()
        row.status = st
        row.reviewed_by = admin.username
        row.reviewed_at = datetime.now(timezone.utc)
        if st == "approved":
            existing = session.exec(
                select(UserAccountAccess).where(
                    UserAccountAccess.user_id == row.user_id,
                    UserAccountAccess.account_id == row.account_id,
                )
            ).first()
            if not existing:
                session.add(
                    UserAccountAccess(
                        id=str(uuid.uuid4()),
                        user_id=row.user_id,
                        account_id=row.account_id,
                    )
                )
        session.add(row)
        session.commit()
        session.refresh(row)
        out = _access_request_to_dict(session, row)
    write_audit(
        admin.username,
        admin.role,
        "access_request_review",
        resource=f"/api/access-requests/{request_id}",
        detail=f"status={out['status']}",
        ip_address=request.client.host if request.client else "",
    )
    await broadcast_json(
        {
            "type": "access_request_updated",
            "request_id": request_id,
            "user_id": out["user_id"],
            "status": out["status"],
        }
    )
    return out
