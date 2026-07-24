"""Resolve a caller's active Kubernetes ToolAccount into a connector (scoped)."""

from __future__ import annotations

from ..auth import User
from ..connectors.kubernetes_connector import KubernetesConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)
from sqlmodel import Session

TOOL_ID = "kubernetes"
CONNECT_MSG = "Connect a Kubernetes account in Tool Registry"
PIN_KEYS = ("kubernetes", "k8s")


def resolve_k8s_tool_account(
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


def k8s_connector_for_account(acc: ToolAccount) -> KubernetesConnector:
    return KubernetesConnector(tool_account_to_connector_dict(acc))


def k8s_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> KubernetesConnector:
    """Raise HTTP 400 when no Kubernetes account is configured for this user."""
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=k8s_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_k8s_connector_for_user(user: User, **kwargs) -> KubernetesConnector | None:
    return try_connector_for_user(k8s_connector_for_user, user, **kwargs)


def try_k8s_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> KubernetesConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=k8s_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )


# Alias used by some callers
try_kubernetes_connector_from_context = try_k8s_connector_from_context
