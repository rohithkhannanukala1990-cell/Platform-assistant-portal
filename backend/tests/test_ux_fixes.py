"""Terminal/editor/workspaces/search UX fixes: capability probe, missing-binary
error path, terminal history REST endpoint, per-user prefs, bulk connector
connection summary, unified_search Workspace/Agent branches, and editor
starter-file seeding."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from backend.database import ToolAccount, engine
from backend.services.terminal_service import store_history
from backend.tests.conftest import auth_headers
from sqlmodel import Session

FAKE_CAPS = {
    "kubectl": {"tool": "kubectl", "available": True, "version": "1.29.9"},
    "helm": {"tool": "helm", "available": True, "version": "3.14.4"},
    "terraform": {"tool": "terraform", "available": False, "version": None},
    "git": {"tool": "git", "available": True, "version": "2.47.3"},
    "aws": {"tool": "aws", "available": False, "version": None},
    "npm": {"tool": "npm", "available": False, "version": None},
    "pip": {"tool": "pip", "available": True, "version": "25.0.1"},
}


# ── capability probe / endpoint ─────────────────────────────────────────────


def test_capabilities_endpoint_reflects_probe(client, admin_token):
    h = auth_headers(admin_token)
    with patch("backend.services.terminal_capabilities.get_capabilities", return_value=FAKE_CAPS):
        res = client.get("/api/terminal/capabilities", headers=h)
    assert res.status_code == 200, res.text
    body = {row["tool"]: row for row in res.json()}
    assert body["kubectl"]["available"] is True
    assert body["kubectl"]["version"] == "1.29.9"
    assert body["terraform"]["available"] is False
    assert body["terraform"]["version"] is None


def test_capabilities_requires_auth(client):
    res = client.get("/api/terminal/capabilities")
    assert res.status_code in (401, 403)


# ── missing-binary error path (safe_executor) ───────────────────────────────


@pytest.mark.asyncio
async def test_missing_known_binary_returns_clean_message():
    from backend.executor.safe_executor import safe_executor

    with patch("backend.services.terminal_capabilities.get_capabilities", return_value=FAKE_CAPS):
        result = await safe_executor.execute(
            ["terraform plan"],
            incident_id=1,
            approved_by="tester",
            context={"role": "Admin", "environment": "development", "tool": "shell", "approved": True},
        )
    assert result["success"] is False
    assert result["policy_effect"] == "missing_binary"
    assert "terraform" in result["policy_reasons"][0]
    assert "not installed" in result["policy_reasons"][0]
    # No raw Python exception text (e.g. "Errno 2") should ever reach the caller.
    assert "Errno" not in result["logs"]


@pytest.mark.asyncio
async def test_unknown_binary_falls_back_to_clean_message():
    from backend.executor.safe_executor import safe_executor

    with patch("backend.services.terminal_capabilities.get_capabilities", return_value=FAKE_CAPS):
        result = await safe_executor.execute(
            ["totally-fake-binary-xyz --version"],
            incident_id=1,
            approved_by="tester",
            context={"role": "Admin", "environment": "development", "tool": "shell", "approved": True},
        )
    assert result["success"] is False
    assert result["policy_effect"] == "missing_binary"
    assert "totally-fake-binary-xyz" in result["policy_reasons"][0]
    assert "Errno" not in result["logs"]


@pytest.mark.asyncio
async def test_present_binary_still_executes():
    from backend.executor.safe_executor import safe_executor

    with patch("backend.services.terminal_capabilities.get_capabilities", return_value=FAKE_CAPS):
        result = await safe_executor.execute(
            ["git --version"],
            incident_id=1,
            approved_by="tester",
            context={"role": "Admin", "environment": "development", "tool": "shell", "approved": True},
        )
    assert result["success"] is True


# ── terminal history REST endpoint ──────────────────────────────────────────


def test_terminal_history_endpoint_returns_stored_commands(client, admin_token):
    h = auth_headers(admin_token)
    store_history(tenant_id="default", username="admin", command="kubectl get pods")
    store_history(tenant_id="default", username="admin", command="helm list")
    res = client.get("/api/terminal/history", headers=h)
    assert res.status_code == 200, res.text
    history = res.json()["history"]
    assert "kubectl get pods" in history
    assert "helm list" in history


# ── user prefs ───────────────────────────────────────────────────────────────


def test_user_pref_round_trip(client, admin_token):
    h = auth_headers(admin_token)
    key = f"test_pref_{uuid.uuid4().hex[:6]}"

    initial = client.get(f"/api/user-prefs/{key}", headers=h)
    assert initial.status_code == 200
    assert initial.json()["value"] is None

    put = client.put(f"/api/user-prefs/{key}", headers=h, json={"value": "1"})
    assert put.status_code == 200
    assert put.json()["value"] == "1"

    after = client.get(f"/api/user-prefs/{key}", headers=h)
    assert after.json()["value"] == "1"


# ── bulk connector connection summary ───────────────────────────────────────


def test_connection_summary_ordered_github_pagerduty_kubernetes_first(client, admin_token):
    h = auth_headers(admin_token)
    res = client.get("/api/tools/connection-summary", headers=h)
    assert res.status_code == 200, res.text
    ids = [row["id"] for row in res.json()]
    assert ids[:3] == ["github", "pagerduty", "kubernetes"]
    assert all("connected" in row for row in res.json())


def test_connection_summary_reflects_connected_account(client, admin_token):
    h = auth_headers(admin_token)
    with Session(engine) as session:
        session.add(
            ToolAccount(
                id=str(uuid.uuid4()),
                tool_id="github",
                account_name="ci-test-account",
                environment="production",
                auth_type="pat",
                status="connected",
                is_active=1,
                tenant_id="default",
                created_by="admin",
            )
        )
        session.commit()
    res = client.get("/api/tools/connection-summary", headers=h)
    row = next(r for r in res.json() if r["id"] == "github")
    assert row["connected"] is True


# ── unified_search Workspace / Agent branches ───────────────────────────────


def test_search_finds_workspaces_and_agents(client, admin_token):
    h = auth_headers(admin_token)
    unique = f"Zeta Search Target {uuid.uuid4().hex[:6]}"
    create = client.post("/api/workspaces", headers=h, json={"name": unique, "description": "for search test"})
    assert create.status_code == 200, create.text

    res = client.get(f"/api/search?q={unique.split()[0]}", headers=h)
    assert res.status_code == 200, res.text
    types = {r["type"] for r in res.json()}
    assert "Workspace" in types

    res2 = client.get("/api/search?q=incident", headers=h)
    assert res2.status_code == 200, res2.text
    agent_hits = [r for r in res2.json() if r["type"] == "Agent"]
    assert any(r["id"] == "incident_agent" for r in agent_hits)


# ── editor starter-file seeding ─────────────────────────────────────────────


def test_editor_starter_files_seeded_once_then_not_reseeded(client, admin_token):
    from backend.auth import User, hash_password
    from sqlmodel import select

    username = f"editor-fresh-{uuid.uuid4().hex[:6]}"
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
    h = auth_headers(login.json()["access_token"])

    first = client.get("/api/editor/files", headers=h)
    assert first.status_code == 200, first.text
    filenames = {f["filename"] for f in first.json()}
    assert {"example-deployment.yaml", "example-module.tf", "example-ci.yml"} <= filenames

    for f in first.json():
        d = client.delete(f"/api/editor/files/{f['id']}", headers=h)
        assert d.status_code == 204

    second = client.get("/api/editor/files", headers=h)
    assert second.json() == []  # not reseeded after user deleted everything
