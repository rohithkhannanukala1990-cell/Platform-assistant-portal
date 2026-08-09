"""Resolve a caller's active Slack ToolAccount into a connector (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.slack_connector import SlackConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "slack"
CONNECT_MSG = "Connect a Slack account in Tool Registry"
PIN_KEYS = ("slack",)


def resolve_slack_tool_account(session: Session, user: User | None = None, **kwargs) -> ToolAccount | None:
    return resolve_tool_account(session, TOOL_ID, user=user, pin_keys=PIN_KEYS, **kwargs)


def slack_connector_for_account(acc: ToolAccount) -> SlackConnector:
    return SlackConnector(tool_account_to_connector_dict(acc))


def slack_connector_for_user(user: User, **kwargs) -> SlackConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=slack_connector_for_account,
        pin_keys=PIN_KEYS,
        **props,
    )


def try_slack_connector_for_user(user: User, **props) -> SlackConnector | None:
    return try_connector_for_user(slack_connector_for_user, user, **props)


def try_slack_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> SlackConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=slack_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
