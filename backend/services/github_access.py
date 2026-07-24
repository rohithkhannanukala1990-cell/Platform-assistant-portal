"""Resolve a caller's active GitHub ToolAccount into a connector (scoped)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from ..auth import User
from ..connectors.github_connector import GitHubConnector
from ..context import PlatformContext
from ..database import ToolAccount, UserContext, engine
from .secrets import decrypt_secret


def tool_account_to_connector_dict(acc: ToolAccount) -> dict[str, Any]:
    """Build connector account dict with decrypted token (server-side only)."""
    plain = decrypt_secret(acc.credentials_vault_ref or "")
    return {
        "tool_id": acc.tool_id,
        "account_name": acc.account_name,
        "account_identifier": acc.account_identifier,
        "instance_url": acc.instance_url,
        "environment": acc.environment,
        "region": acc.region,
        "auth_type": acc.auth_type,
        # Encrypted blob stays for diagnostics; connector uses plaintext token fields.
        "credentials_vault_ref": plain,
        "token": plain,
        "api_token": plain,
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


def _account_in_scope(
    acc: ToolAccount | None,
    *,
    owner_user_id: str | None = None,
    username: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> bool:
    if not acc or acc.tool_id != "github" or int(acc.is_active or 0) != 1:
        return False
    # Explicit ownership
    if owner_user_id and (acc.owner_user_id or "") == owner_user_id:
        return True
    if username and (acc.created_by or "") == username:
        return True
    # Workspace / tenant membership (shared within that boundary)
    if workspace_id and (acc.workspace_id or "") == workspace_id:
        return True
    if tenant_id and (acc.tenant_id or "default") == tenant_id:
        # Only when the account is also owned by this user/creator or has no foreign owner.
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


def resolve_github_tool_account(
    session: Session,
    user: User | None = None,
    account_id_hint: str | None = None,
    *,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> ToolAccount | None:
    """Pick an active GitHub ToolAccount scoped to this user/workspace/tenant.

    Never falls back to "any active GitHub account in the DB".
    """
    owner_user_id, username = _owner_keys(user)
    ws = (workspace_id or getattr(user, "workspace_id", None) or "").strip() or None
    tid = (
        (tenant_id or getattr(user, "tenant_id", None) or "").strip() or None
    )

    if account_id_hint:
        acc = session.get(ToolAccount, account_id_hint)
        if _account_in_scope(
            acc,
            owner_user_id=owner_user_id,
            username=username,
            workspace_id=ws,
            tenant_id=tid,
        ):
            return acc

    if user is not None:
        uid = _context_user_key(user)
        mapping = _active_accounts_map(session, uid)
        # Legacy username-keyed context
        if not mapping and username:
            mapping = _active_accounts_map(session, username)
        aid = mapping.get("github")
        if isinstance(aid, str) and aid.strip():
            acc = session.get(ToolAccount, aid.strip())
            if _account_in_scope(
                acc,
                owner_user_id=owner_user_id,
                username=username,
                workspace_id=ws,
                tenant_id=tid,
            ):
                return acc

    # Owned by this user (owner_user_id or created_by)
    if owner_user_id or username:
        clauses = [
            ToolAccount.tool_id == "github",
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
            if tid:
                # Prefer same tenant when known
                owned = session.exec(q).all()
                for acc in owned:
                    if (acc.tenant_id or "default") == tid or not tid:
                        return acc
                if owned:
                    return owned[0]
            else:
                acc = session.exec(q).first()
                if acc:
                    return acc

    # Workspace-scoped accounts
    if ws:
        acc = session.exec(
            select(ToolAccount)
            .where(
                ToolAccount.tool_id == "github",
                ToolAccount.is_active == 1,
                ToolAccount.workspace_id == ws,
            )
            .order_by(ToolAccount.created_at.desc())
        ).first()
        if acc:
            return acc

    return None


def github_connector_for_account(acc: ToolAccount) -> GitHubConnector:
    return GitHubConnector(tool_account_to_connector_dict(acc))


def github_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> GitHubConnector:
    """Raise HTTP 400 when no GitHub account is configured for this user."""
    with Session(engine) as session:
        acc = resolve_github_tool_account(
            session,
            user=user,
            account_id_hint=account_id_hint,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )
        if not acc:
            raise HTTPException(
                status_code=400,
                detail="Connect a GitHub account in Tool Registry",
            )
        if not (acc.credentials_vault_ref or "").strip():
            raise HTTPException(
                status_code=400,
                detail="Connect a GitHub account in Tool Registry",
            )
        return github_connector_for_account(acc)


def try_github_connector_for_user(user: User, **kwargs) -> GitHubConnector | None:
    try:
        return github_connector_for_user(user, **kwargs)
    except HTTPException:
        return None


def try_github_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> GitHubConnector | None:
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

    aid = None
    raw = accounts.get("github") if accounts else None
    if isinstance(raw, str) and raw.strip():
        aid = raw.strip()

    owns_session = db is None
    session = db or Session(engine)
    try:
        # Resolve a User for UserContext pin when only user_id string is known
        resolved_user = user
        if resolved_user is None and owner_user_id:
            from ..auth import User as AuthUser

            resolved_user = session.get(AuthUser, int(owner_user_id)) if owner_user_id.isdigit() else None
            if resolved_user is None:
                resolved_user = session.exec(
                    select(AuthUser).where(AuthUser.username == owner_user_id)
                ).first()

        acc = resolve_github_tool_account(
            session,
            user=resolved_user,
            account_id_hint=aid,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )
        # If pin was provided but user row missing, still allow pin when ownership matches context ids
        if acc is None and aid:
            candidate = session.get(ToolAccount, aid)
            if _account_in_scope(
                candidate,
                owner_user_id=owner_user_id,
                username=username or owner_user_id,
                workspace_id=workspace_id,
                tenant_id=tenant_id,
            ):
                acc = candidate
        if not acc or not (acc.credentials_vault_ref or "").strip():
            return None
        return github_connector_for_account(acc)
    finally:
        if owns_session:
            session.close()
