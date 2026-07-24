"""Resolve a caller's active PagerDuty ToolAccount into a connector (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.pagerduty_connector import PagerDutyConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "pagerduty"
CONNECT_MSG = "Connect a PagerDuty account in Tool Registry"
PIN_KEYS = ("pagerduty",)


def resolve_pagerduty_tool_account(
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


def pagerduty_connector_for_account(acc: ToolAccount) -> PagerDutyConnector:
    return PagerDutyConnector(tool_account_to_connector_dict(acc))


def pagerduty_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> PagerDutyConnector:
    """Raise HTTP 400 when no PagerDuty account is configured for this user."""
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=pagerduty_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_pagerduty_connector_for_user(user: User, **kwargs) -> PagerDutyConnector | None:
    return try_connector_for_user(pagerduty_connector_for_user, user, **kwargs)


def try_pagerduty_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> PagerDutyConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=pagerduty_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
