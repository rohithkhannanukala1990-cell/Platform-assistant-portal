"""Sends unified-inbox approval items to Slack — the one new "sender" piece
Sprint 6 needs. It decides *whether* an item gets Approve/Reject buttons; the
actual button click is handled entirely by ``routers/slack_interactions.py``,
which dispatches through the same ``services/unified_approvals`` functions as
the web UI. Typed-confirmation and dual-approver items never get buttons here —
those gates exist because the action is too easy to get wrong from a phone.
"""

from __future__ import annotations

import os
from typing import Any

from ..auth import User
from .unified_approvals import get_inbox_item


def _portal_url(item_id: str) -> str:
    base = (os.getenv("FRONTEND_URL") or "https://localhost").rstrip("/")
    return f"{base}/approvals?focus={item_id}"


async def notify_slack_approval(
    item_id: str,
    tenant_id: str,
    channel: str,
    user: User,
) -> dict[str, Any]:
    from .slack_access import try_slack_connector_for_user

    item = get_inbox_item(item_id, tenant_id)
    conn = try_slack_connector_for_user(user, tenant_id=tenant_id)
    if conn is None:
        return {"ok": False, "error": "Slack not connected"}

    detail_url = _portal_url(item_id)
    needs_link_only = bool(item["needs_typed_confirmation"] or item["needs_second_approver"])

    if needs_link_only:
        reason = (
            "requires typed confirmation"
            if item["needs_typed_confirmation"]
            else f"requires a second approver ({len(item['approvers'])}/{item['approvals_required']} so far)"
        )
        text = (
            f"*Approval required — review in portal*\n{item['title']}\n"
            f"_{reason} — too sensitive for a Slack button._\n{detail_url}"
        )
        return await conn.notify_channel(text=text, channel=channel)

    return await conn.post_approval_request(
        channel,
        approval_id=item_id,  # composite "source:native_id" — round-trips the source
        summary=f"{item['title']}\n{item['description'] or ''}".strip(),
        risk=item["risk"],
        detail_url=detail_url,
    )
