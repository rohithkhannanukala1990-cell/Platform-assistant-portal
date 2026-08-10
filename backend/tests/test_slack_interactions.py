"""Sprint 6 — Slack interactivity receiver: signature verification (mandatory,
non-optional), account linking, RBAC parity with the web UI, message updates,
and the button-suppression rule for typed-confirmation/dual-approver items."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

import httpx
import pytest
import respx
from sqlmodel import Session

from backend.database import AgentRun, engine
from backend.db.models.slack import SlackUserLink
from backend.services.artifact_service import propose_artifact
from backend.services.slack_approvals import notify_slack_approval
from backend.tests.conftest import auth_headers

SECRET = "test-signing-secret"
RESPONSE_URL = "https://hooks.slack.com/actions/T123/999/fake"


@pytest.fixture(autouse=True)
def _signing_secret(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SECRET)


def _sign(body: bytes, ts: str) -> str:
    basestring = b"v0:" + ts.encode() + b":" + body
    return "v0=" + hmac.new(SECRET.encode(), basestring, hashlib.sha256).hexdigest()


def _headers(body: bytes, ts: str | None = None, sig: str | None = None) -> dict:
    ts = ts if ts is not None else str(int(time.time()))
    sig = sig if sig is not None else _sign(body, ts)
    return {
        "x-slack-request-timestamp": ts,
        "x-slack-signature": sig,
        "content-type": "application/x-www-form-urlencoded",
    }


def _block_actions_body(action_id: str, value: str, user_id="U1", team_id="T1") -> bytes:
    payload = {
        "type": "block_actions",
        "actions": [{"action_id": action_id, "value": value}],
        "user": {"id": user_id},
        "team": {"id": team_id},
        "channel": {"id": "C1"},
        "message": {"ts": "1700000000.000100"},
        "response_url": RESPONSE_URL,
    }
    return urlencode({"payload": json.dumps(payload)}).encode()


def _seed_pending_agent_run(tenant_id="default"):
    with Session(engine) as session:
        row = AgentRun(
            id=str(uuid.uuid4()),
            agent="cost_agent",
            task="check spend",
            status="pending_approval",
            summary="Approve spend",
            requires_approval=True,
            environment="production",
            tenant_id=tenant_id,
            triggered_by="tester",
        )
        session.add(row)
        session.commit()
        return row.id


def _link(slack_user_id: str, portal_username: str, tenant_id="default", team_id="T1"):
    with Session(engine) as session:
        session.add(
            SlackUserLink(
                tenant_id=tenant_id,
                slack_user_id=slack_user_id,
                slack_team_id=team_id,
                portal_username=portal_username,
            )
        )
        session.commit()


# ── signature verification ──────────────────────────────────────────────────


@respx.mock
def test_valid_signature_accepted(client):
    respx.route(host="hooks.slack.com").mock(return_value=httpx.Response(200, json={}))
    body = _block_actions_body("open_detail", "agent:whatever")
    res = client.post("/api/integrations/slack/interactions", content=body, headers=_headers(body))
    assert res.status_code == 200


def test_invalid_signature_rejected(client):
    body = _block_actions_body("open_detail", "agent:whatever")
    headers = _headers(body)
    headers["x-slack-signature"] = "v0=" + "0" * 64
    res = client.post("/api/integrations/slack/interactions", content=body, headers=headers)
    assert res.status_code == 401


def test_stale_timestamp_rejected(client):
    body = _block_actions_body("open_detail", "agent:whatever")
    old_ts = str(int(time.time()) - 600)  # 10 minutes old
    res = client.post(
        "/api/integrations/slack/interactions",
        content=body,
        headers=_headers(body, ts=old_ts),
    )
    assert res.status_code == 401


def test_missing_signing_secret_rejects_everything(client, monkeypatch):
    monkeypatch.delenv("SLACK_SIGNING_SECRET", raising=False)
    body = _block_actions_body("open_detail", "agent:whatever")
    res = client.post("/api/integrations/slack/interactions", content=body, headers=_headers(body))
    assert res.status_code == 401


# ── account linking / RBAC parity ───────────────────────────────────────────


@respx.mock
def test_unmapped_slack_user_cannot_approve(client):
    respx.route(host="hooks.slack.com").mock(return_value=httpx.Response(200, json={}))
    run_id = _seed_pending_agent_run()
    body = _block_actions_body("approve_request", f"agent:{run_id}", user_id="U-unmapped")
    res = client.post("/api/integrations/slack/interactions", content=body, headers=_headers(body))
    assert res.status_code == 200  # Slack expects 200 even when declined

    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        assert row.status == "pending_approval"  # nothing was approved


@respx.mock
def test_rbac_enforced_identically_to_web_ui(client, admin_token):
    respx.route(host="hooks.slack.com").mock(return_value=httpx.Response(200, json={}))
    # Create a non-admin portal user (every existing approve endpoint requires Admin).
    from backend.auth import User, hash_password

    username = f"nonadmin-{uuid.uuid4().hex[:6]}"
    with Session(engine) as session:
        session.add(
            User(
                username=username,
                email="",
                hashed_password=hash_password("Passw0rd!23"),
                role="User",
                is_active=True,
                tenant_id="default",
            )
        )
        session.commit()
    _link("U-nonadmin", username)

    run_id = _seed_pending_agent_run()
    body = _block_actions_body("approve_request", f"agent:{run_id}", user_id="U-nonadmin")
    res = client.post("/api/integrations/slack/interactions", content=body, headers=_headers(body))
    assert res.status_code == 200

    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        assert row.status == "pending_approval"  # RBAC blocked it, same as the web UI would


@respx.mock
def test_valid_admin_link_approves_and_updates_message(client, admin_token):
    respx.route(host="hooks.slack.com").mock(return_value=httpx.Response(200, json={}))
    _link("U-admin-linked", "admin")
    run_id = _seed_pending_agent_run()
    item_id = f"agent:{run_id}"

    fake_conn = AsyncMock()
    fake_conn.update_message = AsyncMock(return_value={"ok": True})
    with patch("backend.services.slack_access.try_slack_connector_for_user", return_value=fake_conn):
        body = _block_actions_body("approve_request", item_id, user_id="U-admin-linked")
        res = client.post("/api/integrations/slack/interactions", content=body, headers=_headers(body))
    assert res.status_code == 200

    with Session(engine) as session:
        row = session.get(AgentRun, run_id)
        assert row.status != "pending_approval"  # dispatched through approve_item

    fake_conn.update_message.assert_awaited_once()
    call_kwargs = fake_conn.update_message.await_args
    assert call_kwargs.args[0] == "C1"  # channel from the interaction payload
    assert call_kwargs.args[1] == "1700000000.000100"  # message ts from the payload


# ── slash-command linking flow ──────────────────────────────────────────────


@respx.mock
def test_slash_command_links_account(client, admin_token):
    # Use a fresh portal user so this test doesn't collide with other tests'
    # SlackUserLink rows for "admin".
    from backend.auth import User, hash_password

    username = f"link-target-{uuid.uuid4().hex[:6]}"
    with Session(engine) as session:
        session.add(
            User(
                username=username,
                email="",
                hashed_password=hash_password("Passw0rd!23"),
                role="User",
                is_active=True,
                tenant_id="default",
            )
        )
        session.commit()
    login = client.post("/auth/login", data={"username": username, "password": "Passw0rd!23"})
    assert login.status_code == 200, login.text
    user_token = login.json()["access_token"]
    h = auth_headers(user_token)

    start = client.post("/api/integrations/slack/link/start", headers=h)
    assert start.status_code == 200, start.text
    code = start.json()["code"]

    body = urlencode(
        {
            "command": "/portal-link",
            "text": code,
            "user_id": "U-new-link",
            "team_id": "T1",
        }
    ).encode()
    res = client.post("/api/integrations/slack/commands", content=body, headers=_headers(body))
    assert res.status_code == 200
    assert "Linked" in res.json()["text"]

    status = client.get("/api/integrations/slack/link/status", headers=h)
    assert status.status_code == 200
    assert status.json()["linked"] is True
    assert status.json()["slack_user_id"] == "U-new-link"


# ── button suppression for typed-confirmation / dual-approver items ────────


@pytest.mark.asyncio
async def test_typed_confirmation_item_sent_without_buttons(admin_token):
    from backend.auth import User

    approval = propose_artifact(
        tenant_id="default",
        username="tester",
        agent="deploy_agent",
        connector="terraform",
        method="apply_plan",
        params={"workspace": "prod-critical"},
        preview={"require_typed_confirm": True, "confirm_phrase": "prod-critical"},
        grounding="live",
        summary="Destroy 3 resources",
    )
    item_id = f"agent:{approval['agent_run_id']}"

    fake_conn = AsyncMock()
    fake_conn.post_approval_request = AsyncMock(return_value={"ok": True})
    fake_conn.notify_channel = AsyncMock(return_value={"ok": True})

    with Session(engine) as session:
        from sqlmodel import select

        admin = session.exec(select(User).where(User.username == "admin")).first()

    with patch("backend.services.slack_access.try_slack_connector_for_user", return_value=fake_conn):
        await notify_slack_approval(item_id, "default", "#approvals", admin)

    fake_conn.post_approval_request.assert_not_awaited()  # no buttons for typed-confirm items
    fake_conn.notify_channel.assert_awaited_once()


@pytest.mark.asyncio
async def test_normal_item_sent_with_buttons(admin_token):
    from sqlmodel import select

    from backend.auth import User

    run_id = _seed_pending_agent_run()
    item_id = f"agent:{run_id}"

    fake_conn = AsyncMock()
    fake_conn.post_approval_request = AsyncMock(return_value={"ok": True})
    fake_conn.notify_channel = AsyncMock(return_value={"ok": True})

    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()

    with patch("backend.services.slack_access.try_slack_connector_for_user", return_value=fake_conn):
        await notify_slack_approval(item_id, "default", "#approvals", admin)

    fake_conn.post_approval_request.assert_awaited_once()
    _, kwargs = fake_conn.post_approval_request.call_args
    assert kwargs.get("approval_id") == item_id
    fake_conn.notify_channel.assert_not_awaited()
