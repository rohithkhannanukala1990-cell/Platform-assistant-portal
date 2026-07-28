"""Resolve ServiceNow ToolAccount (scoped)."""

from __future__ import annotations

from sqlmodel import Session

from ..auth import User
from ..connectors.servicenow_connector import ServiceNowConnector
from ..context import PlatformContext
from ..database import ToolAccount
from .scoped_tool_access import (
    connector_for_user,
    resolve_tool_account,
    tool_account_to_connector_dict,
    try_connector_for_user,
    try_connector_from_context,
)

TOOL_ID = "servicenow"
CONNECT_MSG = "Connect a ServiceNow account in Tool Registry"
PIN_KEYS = ("servicenow", "snow")


def _account_dict(acc: ToolAccount) -> dict:
    d = tool_account_to_connector_dict(acc)
    plain = (d.get("credentials_vault_ref") or "").strip()
    if plain.startswith("http"):
        d["webhook_url"] = plain
    return d


def resolve_servicenow_tool_account(
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


def servicenow_connector_for_account(acc: ToolAccount) -> ServiceNowConnector:
    return ServiceNowConnector(_account_dict(acc))


def servicenow_connector_for_user(
    user: User,
    *,
    account_id_hint: str | None = None,
    workspace_id: str | None = None,
    tenant_id: str | None = None,
) -> ServiceNowConnector:
    return connector_for_user(
        user,
        tool_id=TOOL_ID,
        connect_message=CONNECT_MSG,
        factory=servicenow_connector_for_account,
        account_id_hint=account_id_hint,
        workspace_id=workspace_id,
        tenant_id=tenant_id,
        pin_keys=PIN_KEYS,
    )


def try_servicenow_connector_for_user(user: User, **kwargs) -> ServiceNowConnector | None:
    return try_connector_for_user(servicenow_connector_for_user, user, **kwargs)


def try_servicenow_connector_from_context(
    context: PlatformContext | dict | None = None,
    tool_accounts: dict | None = None,
    db: Session | None = None,
    *,
    user: User | None = None,
) -> ServiceNowConnector | None:
    return try_connector_from_context(
        tool_id=TOOL_ID,
        factory=servicenow_connector_for_account,
        context=context,
        tool_accounts=tool_accounts,
        db=db,
        user=user,
        pin_keys=PIN_KEYS,
    )
