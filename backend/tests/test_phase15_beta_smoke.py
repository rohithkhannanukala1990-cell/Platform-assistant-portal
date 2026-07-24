"""Phase 15 — Beta smoke: health/ready, login, llm status, github repos."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.tests.conftest import auth_headers

pytestmark = pytest.mark.smoke


def test_health_ready(client):
    h = client.get("/health")
    assert h.status_code == 200
    assert h.json().get("status") == "ok"

    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json().get("status") == "ready"


def test_login_smoke(client):
    r = client.post(
        "/auth/login",
        data={"username": "admin", "password": "Admin123!"},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("access_token")


def test_llm_status_smoke(client, admin_token):
    r = client.get("/api/llm/status", headers=auth_headers(admin_token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "default_model" in body or "providers" in body


def test_github_repos_400_without_account(client, admin_token):
    h = auth_headers(admin_token)
    accounts = client.get("/api/tools/github/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/github/accounts/{acc['id']}", headers=h)

    r = client.get("/api/github/repos", headers=h)
    assert r.status_code == 400
    assert "Connect a GitHub account" in (r.json().get("detail") or "")


def test_github_repos_200_with_mock(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/github/accounts",
        headers=h,
        json={
            "account_name": "phase15-smoke-gh",
            "environment": "development",
            "auth_type": "pat",
            "account_identifier": "",
            "credentials_vault_ref": "ghp_test_token_phase15_smoke",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]

    fake = [
        {
            "id": 1,
            "name": "smoke",
            "full_name": "acme/smoke",
            "private": False,
            "html_url": "https://github.com/acme/smoke",
            "default_branch": "main",
        }
    ]
    try:
        with patch(
            "backend.routers.github_ops.github_connector_for_user"
        ) as mock_resolve:
            connector = AsyncMock()
            connector.list_repos = AsyncMock(return_value=fake)
            mock_resolve.return_value = connector
            r = client.get("/api/github/repos", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()[0]["full_name"] == "acme/smoke"
    finally:
        client.delete(f"/api/tools/github/accounts/{aid}", headers=h)
