"""Resolve a caller's active Prometheus ToolAccount into a connector (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.prometheus_connector import PrometheusConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "prometheus"
CONNECT_MSG = "Connect a Prometheus account in Tool Registry"
PIN_KEYS = ("prometheus",)


def resolve_prometheus_tool_account(
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


def prometheus_connector_for_account(acc: ToolAccount) -> PrometheusConnector:
    return PrometheusConnector(tool_account_to_connector_dict(acc))


def prometheus_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> PrometheusConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=prometheus_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_prometheus_connector_for_user(user: User, **kwargs) -> PrometheusConnector | None:
    return try_connector_for_user(prometheus_connector_for_user, user, **kwargs)


def try_prometheus_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> PrometheusConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=prometheus_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
