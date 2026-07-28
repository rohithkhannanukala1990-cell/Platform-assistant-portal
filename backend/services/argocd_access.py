"""Resolve a caller's active ArgoCD ToolAccount into a connector (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.argocd_connector import ArgoCDConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "argocd"
CONNECT_MSG = "Connect an ArgoCD account in Tool Registry"
PIN_KEYS = ("argocd", "argo")


def resolve_argocd_tool_account(
    session: Session,
    user: User | None = None,
    account_id_hint: str | None = None,
    *,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> ToolAccount | None:
    return resolve_tool_account(
        session,
        TOOL_ID,
        user=user,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def argocd_connector_for_account(acc: ToolAccount) -> ArgoCDConnector:
    return ArgoCDConnector(tool_account_to_connector_dict(acc))


def argocd_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> ArgoCDConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=argocd_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_argocd_connector_for_user(user: User, **kwargs) -> ArgoCDConnector | None:
    return try_connector_for_user(argocd_connector_for_user, user, **kwargs)


def try_argocd_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> ArgoCDConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=argocd_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
