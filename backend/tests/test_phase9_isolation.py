"""Phase 9: tenant + workspace isolation hard-fail."""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.database import Tool, ToolAccount, save_incident
from backend.services.isolation import assert_same_tenant, require_tenant
from backend.tests.conftest import auth_headers
from fastapi import HTTPException


def _make_user(username: str, *, tenant_id: str, role: str = "User") -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.tenant_id = tenant_id
            existing.role = role
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password("Password123!"),
            role=role,
            is_active=True,
            tenant_id=tenant_id,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def _login(client, username: str) -> str:
    r = client.post(
        "/auth/login",
        data={"username": username, "password": "Password123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_user_a_cannot_read_user_b_incident(client):
    user_a = _make_user("phase9-inc-a", tenant_id="tenant-a")
    user_b = _make_user("phase9-inc-b", tenant_id="tenant-b")
    _ = user_a
    token_b = _login(client, user_b.username)

    inc = save_incident(
        {
            "severity": "Low",
            "summary": "tenant-a only",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": [],
            "commands": [],
            "raw_logs": "x",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "tenant-a",
        }
    )

    # User B (other tenant) must get 404
    r = client.get(
        f"/api/incidents/{inc.id}",
        headers=auth_headers(token_b),
    )
    assert r.status_code == 404

    token_a = _login(client, "phase9-inc-a")
    ok = client.get(f"/api/incidents/{inc.id}", headers=auth_headers(token_a))
    assert ok.status_code == 200
    assert ok.json()["id"] == inc.id


def test_user_a_cannot_list_user_b_tool_accounts(client):
    user_a = _make_user("phase9-tool-a", tenant_id="tenant-tools-a")
    user_b = _make_user("phase9-tool-b", tenant_id="tenant-tools-b")
    token_a = _login(client, user_a.username)
    token_b = _login(client, user_b.username)

    with Session(engine) as session:
        if session.get(Tool, "github") is None:
            session.add(
                Tool(id="github", name="GitHub", category="source_control", description="")
            )
            session.commit()

    create = client.post(
        "/api/tools/github/accounts",
        headers=auth_headers(token_a),
        json={
            "account_name": "a-only-gh",
            "environment": "development",
            "auth_type": "pat",
            "credentials_vault_ref": "ghp_phase9_a",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]

    listed_b = client.get(
        "/api/tools/github/accounts",
        headers=auth_headers(token_b),
    )
    assert listed_b.status_code == 200
    ids = {a["id"] for a in listed_b.json()}
    assert aid not in ids

    listed_a = client.get(
        "/api/tools/github/accounts",
        headers=auth_headers(token_a),
    )
    assert aid in {a["id"] for a in listed_a.json()}


def test_user_a_cannot_load_user_b_user_context(client):
    user_a = _make_user("phase9-ctx-a", tenant_id="tenant-ctx-a")
    user_b = _make_user("phase9-ctx-b", tenant_id="tenant-ctx-b")
    token_a = _login(client, user_a.username)
    # Ensure B has a context row
    token_b = _login(client, user_b.username)
    assert client.get("/api/context", headers=auth_headers(token_b)).status_code == 200

    r = client.get(
        f"/api/context/users/{user_b.id}",
        headers=auth_headers(token_a),
    )
    assert r.status_code == 404


def test_agent_run_fills_user_id_from_auth(client):
    from backend.routers.agents import RunAgentRequest, _build_platform_context
    from starlette.requests import Request

    user = _make_user("phase9-agent", tenant_id="tenant-agent")
    token = _login(client, user.username)
    _ = token

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/agents/run",
        "raw_path": b"/api/agents/run",
        "query_string": b"",
        "headers": [],
        "client": ("test", 50000),
        "server": ("test", 80),
    }
    request = Request(scope)
    request.state.tenant_id = "tenant-agent"
    request.state.workspace_id = "ws-phase9"
    body = RunAgentRequest(task="noop", context={"user_id": "", "tool_accounts": {}})
    ctx = _build_platform_context(request, body, user)
    assert ctx.user_id == str(user.id)
    assert ctx.tenant_id == "tenant-agent"


def test_assert_same_tenant_returns_404():
    try:
        assert_same_tenant("tenant-a", "tenant-b")
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_enforce_workspace_isolation_blocks_without_workspace(client, monkeypatch):
    monkeypatch.setenv("ENFORCE_WORKSPACE_ISOLATION", "true")
    user = _make_user("phase9-enforce", tenant_id="tenant-enforce")
    # Clear default workspace so middleware has none
    with Session(engine) as session:
        row = session.get(User, user.id)
        row.workspace_id = None
        session.add(row)
        session.commit()
    token = _login(client, user.username)
    r = client.get("/api/incidents", headers=auth_headers(token))
    assert r.status_code == 403
    assert r.json().get("code") == "workspace_required" or "workspace" in str(
        r.json().get("detail", "")
    ).lower()
