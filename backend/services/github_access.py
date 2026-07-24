"""Resolve a caller's active GitHub ToolAccount into a connector."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from ..auth import User
from ..connectors.github_connector import GitHubConnector
from ..database import ToolAccount, UserContext, engine


def tool_account_to_connector_dict(acc: ToolAccount) -> dict[str, Any]:
    return {
        "tool_id": acc.tool_id,
        "account_name": acc.account_name,
        "account_identifier": acc.account_identifier,
        "instance_url": acc.instance_url,
        "environment": acc.environment,
        "region": acc.region,
        "auth_type": acc.auth_type,
        "credentials_vault_ref": acc.credentials_vault_ref,
        "token": acc.credentials_vault_ref,
        "api_token": acc.credentials_vault_ref,
    }


def _context_user_key(user: User) -> str:
    if getattr(user, "id", None) is not None:
        return str(user.id)
    return str(user.username)


def resolve_github_tool_account(
    session: Session,
    user: User | None = None,
    account_id_hint: str | None = None,
) -> ToolAccount | None:
    """Pick the active GitHub ToolAccount for a user (context pin → any active)."""
    if account_id_hint:
        acc = session.get(ToolAccount, account_id_hint)
        if acc and acc.tool_id == "github" and acc.is_active == 1:
            return acc

    if user is not None:
        uid = _context_user_key(user)
        ctx = session.get(UserContext, uid)
        if ctx and ctx.active_accounts:
            try:
                mapping = json.loads(ctx.active_accounts or "{}")
            except (json.JSONDecodeError, TypeError, ValueError):
                mapping = {}
            if isinstance(mapping, dict):
                aid = mapping.get("github")
                if isinstance(aid, str) and aid:
                    acc = session.get(ToolAccount, aid)
                    if acc and acc.tool_id == "github" and acc.is_active == 1:
                        return acc

    return session.exec(
        select(ToolAccount)
        .where(
            ToolAccount.tool_id == "github",
            ToolAccount.is_active == 1,
        )
        .order_by(ToolAccount.created_at.desc())
    ).first()


def github_connector_for_account(acc: ToolAccount) -> GitHubConnector:
    return GitHubConnector(tool_account_to_connector_dict(acc))


def github_connector_for_user(user: User) -> GitHubConnector:
    """Raise HTTP 400 when no GitHub account is configured."""
    with Session(engine) as session:
        acc = resolve_github_tool_account(session, user=user)
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


def try_github_connector_for_user(user: User) -> GitHubConnector | None:
    try:
        return github_connector_for_user(user)
    except HTTPException:
        return None


def try_github_connector_from_context(
    tool_accounts: dict | None,
    db: Session | None = None,
) -> GitHubConnector | None:
    """Agent-friendly resolver using PlatformContext.tool_accounts mapping."""
    aid = None
    if isinstance(tool_accounts, dict):
        raw = tool_accounts.get("github")
        if isinstance(raw, str) and raw.strip():
            aid = raw.strip()

    owns_session = db is None
    session = db or Session(engine)
    try:
        acc = None
        if aid:
            row = session.get(ToolAccount, aid)
            if row and row.tool_id == "github" and row.is_active == 1:
                acc = row
        if acc is None:
            acc = session.exec(
                select(ToolAccount)
                .where(ToolAccount.tool_id == "github", ToolAccount.is_active == 1)
                .order_by(ToolAccount.created_at.desc())
            ).first()
        if not acc or not (acc.credentials_vault_ref or "").strip():
            return None
        return github_connector_for_account(acc)
    finally:
        if owns_session:
            session.close()
