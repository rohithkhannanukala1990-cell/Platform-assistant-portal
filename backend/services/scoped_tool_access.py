"""Shared scoped ToolAccount resolution (no global fallback)."""

from __future__ import annotations

import json
from typing import Any, Callable, TypeVar

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from ..auth import User
from ..context import PlatformContext
from ..database import ToolAccount, UserContext, engine
from .secrets import decrypt_secret

T = TypeVar("T")


def tool_account_to_connector_dict(acc: ToolAccount) -> dict[str, Any]:
    """Build connector account dict with decrypted secret (server-side only)."""
    plain = decrypt_secret(acc.credentials_vault_ref or "")
    return {
        "tool_id": acc.tool_id,
        "account_name": acc.account_name,
        "account_identifier": acc.account_identifier,
        "instance_url": acc.instance_url,
        "environment": acc.environment,
        "region": acc.region,
        "auth_type": acc.auth_type,
        "credentials_vault_ref": plain,
        "token": plain,
        "api_token": plain,
        "api_key": plain,
        "kubeconfig": plain,
    }


def _context_user_key(user: User) -> str:
    if getattr(user, "id", None) is not None:
        return str(user.id)
    return str(user.username)


def _owner_keys(user: User | None) -> tuple[str | None, str | None]:
    if user is None:
        return None, None
    uid = str(user.id) if getattr(user, "id", None) is not None else None
    uname = (user.username or "").strip() or None
    return uid, uname


def account_in_scope(
    acc: ToolAccount | None,
    *,
    tool_id: str,
    owner_user_id: str | None = None,
    username: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> bool:
    if not acc or acc.tool_id != tool_id or int(acc.is_active or 0) != 1:
        return False
    if owner_user_id and (acc.owner_user_id or "") == owner_user_id:
        return True
    if username and (acc.created_by or "") == username:
        return True
    if workspace_id and (acc.workspace_id or "") == workspace_id:
        return True
    if tenant_id and (acc.tenant_id or "default") == tenant_id:
        foreign_owner = (acc.owner_user_id or "").strip()
        if not foreign_owner or (owner_user_id and foreign_owner == owner_user_id):
            return True
        if username and (acc.created_by or "") == username:
            return True
        return False
    return False


def _active_accounts_map(session: Session, user_key: str) -> dict[str, str]:
    ctx = session.get(UserContext, user_key)
    if not ctx or not ctx.active_accounts:
        return {}
    try:
        mapping = json.loads(ctx.active_accounts or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        mapping = {}
    return mapping if isinstance(mapping, dict) else {}


def resolve_tool_account(
    session: Session,
    tool_id: str,
    user: User | None = None,
    account_id_hint: str | None = None,
    *,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
    pin_keys: tuple[str, ...] = (),
) -> ToolAccount | None:
    """Pick an active ToolAccount scoped to this user/workspace/tenant.

    Never falls back to "any active account in the DB".
    """
    owner_user_id, username = _owner_keys(user)
    ws = (workspace_id or getattr(user, "workspace_id", None) or "").strip() or None
    tid = (tenant_id or getattr(user, "tenant_id", None) or "").strip() or None
    pins = pin_keys or (tool_id,)

    def _in_scope(acc: ToolAccount | None) -> bool:
        return account_in_scope(
            acc,
            tool_id=tool_id,
            owner_user_id=owner_user_id,
            username=username,
            workspace_id=ws,
            tenant_id=tid,
        )

    if account_id_hint:
        acc = session.get(ToolAccount, account_id_hint)
        if _in_scope(acc):
            return acc

    if user is not None:
        uid = _context_user_key(user)
        mapping = _active_accounts_map(session, uid)
        if not mapping and username:
            mapping = _active_accounts_map(session, username)
        for key in pins:
            aid = mapping.get(key)
            if isinstance(aid, str) and aid.strip():
                acc = session.get(ToolAccount, aid.strip())
                if _in_scope(acc):
                    return acc

    if owner_user_id or username:
        clauses = [
            ToolAccount.tool_id == tool_id,
            ToolAccount.is_active == 1,
        ]
        ownership = []
        if owner_user_id:
            ownership.append(ToolAccount.owner_user_id == owner_user_id)
        if username:
            ownership.append(ToolAccount.created_by == username)
        if ownership:
            q = (
                select(ToolAccount)
                .where(*clauses, or_(*ownership))
                .order_by(ToolAccount.created_at.desc())
            )
            owned = session.exec(q).all()
            if tid:
                for acc in owned:
                    if (acc.tenant_id or "default") == tid:
                        return acc
            if owned:
                return owned[0]

    if ws:
        acc = session.exec(
            select(ToolAccount)
            .where(
                ToolAccount.tool_id == tool_id,
                ToolAccount.is_active == 1,
                ToolAccount.workspace_id == ws,
            )
            .order_by(ToolAccount.created_at.desc())
        ).first()
        if acc:
            return acc

    return None


def connector_for_user(
    user: User,
    *,
    tool_id: str,
    connect_message: str,
    factory: Callable[[ToolAccount], T],
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
    pin_keys: tuple[str, ...] = (),
) -> T:
    with Session(engine) as session:
        acc = resolve_tool_account(
            session,
            tool_id,
            user=user,
            account_id_hint=account_id_hint,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            pin_keys=pin_keys,
        )
        if not acc or not (acc.credentials_vault_ref or "").strip():
            raise HTTPException(status_code=400, detail=connect_message)
        return factory(acc)


def try_connector_for_user(fn: Callable[..., T], *args, **kwargs) -> T | None:
    try:
        return fn(*args, **kwargs)
    except HTTPException:
        return None


def try_connector_from_context(
    *,
    tool_id: str,
    factory: Callable[[ToolAccount], T],
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    user: User | None = None,
    pin_keys: tuple[str, ...] = (),
) -> T | None:
    """Agent-friendly resolver — scoped via PlatformContext; no global fallback."""
    ctx = context
    if isinstance(context, dict):
        ctx = PlatformContext.from_dict(context)
    accounts = tool_accounts
    if accounts is None and isinstance(ctx, PlatformContext):
        accounts = ctx.tool_accounts
    accounts = accounts if isinstance(accounts, dict) else {}

    owner_user_id = None
    username = None
    workspace_id = None
    tenant_id = None
    if isinstance(ctx, PlatformContext):
        owner_user_id = (ctx.user_id or "").strip() or None
        workspace_id = (ctx.workspace_id or "").strip() or None
        tenant_id = (ctx.tenant_id or "").strip() or None
    if user is not None:
        owner_user_id = owner_user_id or (
            str(user.id) if getattr(user, "id", None) is not None else None
        )
        username = (user.username or "").strip() or None
        workspace_id = workspace_id or getattr(user, "workspace_id", None)
        tenant_id = tenant_id or getattr(user, "tenant_id", None)

    pins = pin_keys or (tool_id,)
    aid = None
    for key in pins:
        raw = accounts.get(key) if accounts else None
        if isinstance(raw, str) and raw.strip():
            aid = raw.strip()
            break

    owns_session = db is None
    session = db or Session(engine)
    try:
        resolved_user = user
        if resolved_user is None and owner_user_id:
            from ..auth import User as AuthUser

            resolved_user = (
                session.get(AuthUser, int(owner_user_id)) if owner_user_id.isdigit() else None
            )
            if resolved_user is None:
                resolved_user = session.exec(
                    select(AuthUser).where(AuthUser.username == owner_user_id)
                ).first()

        acc = resolve_tool_account(
            session,
            tool_id,
            user=resolved_user,
            account_id_hint=aid,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            pin_keys=pins,
        )
        if acc is None and aid:
            candidate = session.get(ToolAccount, aid)
            if account_in_scope(
                candidate,
                tool_id=tool_id,
                owner_user_id=owner_user_id,
                username=username or owner_user_id,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
            ):
                acc = candidate
        if not acc or not (acc.credentials_vault_ref or "").strip():
            return None
        return factory(acc)
    finally:
        if owns_session:
            session.close()
