"""Slack interactivity receiver + slash-command account linking.

Every request here is signature-verified before anything else runs (mandatory,
never configurable off — see ``services/slack_signature.py``). Button clicks are
dispatched through ``services/unified_approvals`` — the exact same approve/reject
functions the web inbox calls — so Slack can never grant a permission the portal
UI wouldn't.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from ..auth import User, get_current_user, normalize_role
from ..database import engine
from ..db.models.slack import SlackLinkCode, SlackUserLink
from ..services.isolation import require_tenant
from ..services.slack_signature import verify_slack_request
from ..services.unified_approvals import approve_item, reject_item

router = APIRouter(prefix="/api/integrations/slack", tags=["slack-integration"])

LINK_CODE_TTL_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    # SQLite round-trips datetimes as naive; normalize before comparing.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _verify_or_401(request: Request) -> None:
    raw = await request.body()
    timestamp = request.headers.get("x-slack-request-timestamp", "")
    signature = request.headers.get("x-slack-signature", "")
    if not verify_slack_request(timestamp=timestamp, body=raw, signature=signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")


async def _post_ephemeral(response_url: str, text: str) -> None:
    if not response_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                response_url,
                json={"response_type": "ephemeral", "replace_original": False, "text": text},
            )
    except Exception:
        pass  # best-effort — the interaction still returns 200 either way


def _resolve_link(slack_user_id: str, team_id: Optional[str]) -> Optional[SlackUserLink]:
    with Session(engine) as session:
        if team_id:
            row = session.exec(
                select(SlackUserLink).where(
                    SlackUserLink.slack_user_id == slack_user_id,
                    SlackUserLink.slack_team_id == team_id,
                )
            ).first()
            if row:
                return row
        return session.exec(
            select(SlackUserLink).where(SlackUserLink.slack_user_id == slack_user_id)
        ).first()


def _load_portal_user(username: str) -> Optional[User]:
    with Session(engine) as session:
        return session.exec(select(User).where(User.username == username)).first()


@router.post("/interactions")
async def slack_interactions(request: Request):
    await _verify_or_401(request)
    form = await request.form()
    payload_raw = form.get("payload")
    try:
        payload: dict[str, Any] = json.loads(payload_raw or "{}")
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid interaction payload")

    actions = payload.get("actions") or []
    action = actions[0] if actions else {}
    action_id = action.get("action_id")
    value = str(action.get("value") or "")
    response_url = payload.get("response_url") or ""

    if action_id == "open_detail" or action_id not in {"approve_request", "reject_request"}:
        return {}  # plain link button / unknown action — nothing to dispatch

    slack_user = (payload.get("user") or {}).get("id") or ""
    team_id = (payload.get("team") or {}).get("id")
    container = payload.get("container") or {}
    channel_id = (payload.get("channel") or {}).get("id") or container.get("channel_id") or ""
    message_ts = (payload.get("message") or {}).get("ts") or container.get("message_ts") or ""

    link = _resolve_link(slack_user, team_id)
    if link is None:
        await _post_ephemeral(
            response_url,
            "Your Slack account isn't linked to a portal account yet. "
            "Open the portal → Settings → Slack to generate a linking code, "
            "then run `/portal-link <code>` here.",
        )
        return {}

    user = _load_portal_user(link.portal_username)
    if user is None or not user.is_active:
        await _post_ephemeral(response_url, "Your linked portal account is no longer active.")
        return {}

    if normalize_role(user.role) != "Admin":
        # Identical RBAC to the web UI — every existing approve/reject endpoint
        # in this app requires Admin, so Slack cannot grant more than the portal does.
        await _post_ephemeral(response_url, "Your portal account doesn't have permission to approve this.")
        return {}

    item_id = value if ":" in value else f"agent:{value}"  # legacy senders pass a bare AgentRun id

    try:
        if action_id == "approve_request":
            await approve_item(item_id, link.tenant_id, user)
            decision = "Approved"
        else:
            await reject_item(item_id, link.tenant_id, user, reason=f"Rejected via Slack by {user.username}")
            decision = "Rejected"
    except HTTPException as exc:
        await _post_ephemeral(response_url, f"Could not process: {exc.detail}")
        return {}

    if channel_id and message_ts:
        try:
            from ..services.slack_access import try_slack_connector_for_user

            conn = try_slack_connector_for_user(user, tenant_id=link.tenant_id)
            if conn is not None:
                when = _now().strftime("%Y-%m-%d %H:%M UTC")
                await conn.update_message(
                    channel_id,
                    message_ts,
                    text=f"{decision} by @{user.username} at {when}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*{decision}* by @{user.username} at {when}",
                            },
                        }
                    ],
                )
        except Exception:
            pass  # decision already executed — message update is best-effort

    return {}


@router.post("/commands")
async def slack_commands(request: Request):
    await _verify_or_401(request)
    form = await request.form()
    command = str(form.get("command") or "").strip()
    text = str(form.get("text") or "").strip()
    slack_user_id = str(form.get("user_id") or "").strip()
    team_id = str(form.get("team_id") or "").strip() or None

    if command != "/portal-link":
        return {"response_type": "ephemeral", "text": f"Unknown command '{command}'."}

    if not text or not slack_user_id:
        return {
            "response_type": "ephemeral",
            "text": "Usage: `/portal-link <code>` — get a code from the portal under Settings → Slack.",
        }

    now = _now()
    with Session(engine) as session:
        code_row = session.get(SlackLinkCode, text)
        if not code_row or code_row.used_at is not None or _aware(code_row.expires_at) < now:
            return {
                "response_type": "ephemeral",
                "text": "That code is invalid or has expired. Generate a new one from Settings → Slack.",
            }

        existing = session.exec(
            select(SlackUserLink).where(
                SlackUserLink.slack_user_id == slack_user_id,
                SlackUserLink.slack_team_id == team_id,
            )
        ).first()
        if existing:
            existing.portal_username = code_row.portal_username
            existing.tenant_id = code_row.tenant_id
            existing.linked_at = now
            session.add(existing)
        else:
            session.add(
                SlackUserLink(
                    tenant_id=code_row.tenant_id,
                    slack_user_id=slack_user_id,
                    slack_team_id=team_id,
                    portal_username=code_row.portal_username,
                    linked_at=now,
                )
            )
        code_row.used_at = now
        session.add(code_row)
        session.commit()
        linked_username = code_row.portal_username

    return {"response_type": "ephemeral", "text": f"Linked to portal user *{linked_username}* ✅"}


@router.post("/link/start")
def start_slack_link(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8].upper()
    expires_at = _now() + timedelta(minutes=LINK_CODE_TTL_MINUTES)
    with Session(engine) as session:
        session.add(
            SlackLinkCode(
                code=code,
                tenant_id=tenant_id,
                portal_username=current_user.username,
                expires_at=expires_at,
            )
        )
        session.commit()
    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "instructions": f"In Slack, run: /portal-link {code}",
    }


@router.get("/link/status")
def slack_link_status(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        row = session.exec(
            select(SlackUserLink).where(
                SlackUserLink.portal_username == current_user.username,
                SlackUserLink.tenant_id == tenant_id,
            )
        ).first()
    return {
        "linked": row is not None,
        "slack_user_id": row.slack_user_id if row else None,
        "linked_at": row.linked_at.isoformat() if row else None,
    }
