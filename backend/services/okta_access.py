"""Resolve a caller's active Okta ToolAccount into a connector (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.okta_connector import OktaConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "okta"
CONNECT_MSG = "Connect an Okta account in Tool Registry"
PIN_KEYS = ("okta",)


def resolve_okta_tool_account(session: Session, user: User | None = None, **kwargs) -> ToolAccount | None:
    return resolve_tool_account(session, TOOL_ID, user=user, pin_keys=PIN_KEYS, **kwargs)


def okta_connector_for_account(acc: ToolAccount) -> OktaConnector:
    return OktaConnector(tool_account_to_connector_dict(acc))


def okta_connector_for_user(user: User, **props) -> OktaConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=okta_connector_for_account,
        pin_keys=PIN_KEYS,
        **props,
    )


def try_okta_connector_for_user(user: User, **props) -> OktaConnector | None:
    return try_connector_for_user(okta_connector_for_user, user, **props)


def try_okta_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> OktaConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=okta_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
