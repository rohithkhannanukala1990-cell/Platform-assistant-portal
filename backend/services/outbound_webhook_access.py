"""Resolve outbound webhook ToolAccount (scoped, no global fallback)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.outbound_webhook_connector import OutboundWebhookConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "outbound_webhook"
CONNECT_MSG = "Connect an Outbound Webhook account in Tool Registry"
PIN_KEYS = ("outbound_webhook", "http_webhook", "webhook")


def _account_dict(acc: ToolAccount) -> dict:
    d = tool_account_to_connector_dict(acc)
    plain = (d.get("credentials_vault_ref") or "").strip()
    if (d.get("instance_url") or "").startswith("http"):
        d["webhook_url"] = d["instance_url"]
    elif plain.startswith("http"):
        d["webhook_url"] = plain
        d["instance_url"] = plain
    return d


def resolve_outbound_webhook_tool_account(
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


def outbound_webhook_connector_for_account(acc: ToolAccount) -> OutboundWebhookConnector:
    return OutboundWebhookConnector(_account_dict(acc))


def outbound_webhook_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> OutboundWebhookConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=outbound_webhook_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_outbound_webhook_connector_for_user(user: User, **kwargs) -> OutboundWebhookConnector | None:
    return try_connector_for_user(outbound_webhook_connector_for_user, user, **kwargs)


def try_outbound_webhook_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> OutboundWebhookConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=outbound_webhook_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
