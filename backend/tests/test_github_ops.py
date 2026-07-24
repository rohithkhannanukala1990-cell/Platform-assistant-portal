"""Phase 6: GitHub ops routes (read-only) with mocked GitHub HTTP."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.tests.conftest import auth_headers


def test_github_repos_requires_auth(client):
    r = client.get("/api/github/repos")
    assert r.status_code in (401, 403)


def test_github_repos_400_when_no_account(client, admin_token):
    h = auth_headers(admin_token)
    # Ensure no active github accounts with credentials
    accounts = client.get("/api/tools/github/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/github/accounts/{acc['id']}", headers=h)

    r = client.get("/api/github/repos", headers=h)
    assert r.status_code == 400
    detail = r.json().get("detail") or ""
    assert "Connect a GitHub account in Tool Registry" in detail


def test_github_repos_list_mapping(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/github/accounts",
        headers=h,
        json={
            "account_name": "phase6-gh",
            "environment": "development",
            "auth_type": "pat",
            "account_identifier": "",
            "credentials_vault_ref": "ghp_test_token_phase6_not_real",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]

    fake_repos = [
        {
            "id": 1,
            "name": "alpha",
            "full_name": "acme/alpha",
            "private": False,
            "html_url": "https://github.com/acme/alpha",
            "default_branch": "main",
        },
        {
            "id": 2,
            "name": "beta",
            "full_name": "acme/beta",
            "private": True,
            "html_url": "https://github.com/acme/beta",
            "default_branch": "develop",
        },
    ]

    with patch(
        "backend.routers.github_ops.github_connector_for_user"
    ) as mock_resolve:
        connector = AsyncMock()
        connector.list_repos = AsyncMock(return_value=fake_repos)
        mock_resolve.return_value = connector

        r = client.get("/api/github/repos?per_page=10", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert body[0]["full_name"] == "acme/alpha"
    assert body[0]["html_url"] == "https://github.com/acme/alpha"
    assert "ghp_test_token" not in r.text
    connector.list_repos.assert_awaited()

    client.delete(f"/api/tools/github/accounts/{aid}", headers=h)


def test_github_connector_list_repos_http_mapping():
    import asyncio

    from backend.connectors.github_connector import GitHubConnector

    connector = GitHubConnector(
        {"tool_id": "github", "token": "ghp_secret_should_not_leak"}
    )

    class FakeResp:
        status_code = 200
        text = "[]"

        def json(self):
            return [
                {
                    "id": 99,
                    "name": "svc",
                    "full_name": "org/svc",
                    "private": False,
                    "html_url": "https://github.com/org/svc",
                    "default_branch": "main",
                    "extra_field": "ignored",
                }
            ]

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=FakeResp())

    with patch(
        "backend.connectors.github_connector.httpx.AsyncClient",
        return_value=fake_client,
    ):
        repos = asyncio.run(connector.list_repos(per_page=5))

    assert repos == [
        {
            "id": 99,
            "name": "svc",
            "full_name": "org/svc",
            "private": False,
            "html_url": "https://github.com/org/svc",
            "default_branch": "main",
        }
    ]
    called_url = fake_client.get.await_args.args[0]
    assert called_url.endswith("/user/repos")
