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


def _account_dict(acc: ToolAccount) -> dict:
    d = tool_account_to_connector_dict(acc)
    # Incoming webhook URL may live in instance_url or decrypted secret.
    plain = (d.get("credentials_vault_ref") or "").strip()
    if plain.startswith("http") and not (d.get("instance_url") or "").startswith("http"):
        d["webhook_url"] = plain
        d["instance_url"] = d.get("instance_url") or plain
    elif (d.get("instance_url") or "").startswith("https://hooks.slack.com"):
        d["webhook_url"] = d["instance_url"]
    return d


def resolve_slack_tool_account(
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


def slack_connector_for_account(acc: ToolAccount) -> SlackConnector:
    return SlackConnector(_account_dict(acc))


def slack_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> SlackConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=slack_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_slack_connector_for_user(user: User, **kwargs) -> SlackConnector | None:
    return try_connector_for_user(slack_connector_for_user, user, **kwargs)


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
