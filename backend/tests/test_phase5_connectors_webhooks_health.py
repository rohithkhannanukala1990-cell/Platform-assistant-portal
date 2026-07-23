"""Phase 5: GitHub connector errors, webhook secrets, connector health probes."""

from __future__ import annotations

import hashlib
import hmac
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.connectors.github_connector import GitHubAPIError, GitHubConnector
from backend.context import PlatformContext
from backend.health import _sync_tool_accounts_probe
from backend.observability.metrics import CONNECTOR_ERRORS_TOTAL
from backend.webhooks.security import require_valid_signature, verify_webhook_signature


def test_github_get_maps_http_status_to_structured_errors():
    connector = GitHubConnector({"tool_id": "github"})

    class FakeResp:
        def __init__(self, status_code: int, text: str = ""):
            self.status_code = status_code
            self.text = text

        def json(self):
            return {}

    cases = {
        401: "auth_failed",
        403: "auth_failed",
        404: "not_found",
        429: "rate_limited",
        500: "network_error",
    }
    for status, expected in cases.items():
        fake_client = MagicMock()
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=None)
        fake_client.get = AsyncMock(return_value=FakeResp(status, "boom"))
        with patch("backend.connectors.github_connector.httpx.AsyncClient", return_value=fake_client):
            with pytest.raises(GitHubAPIError) as exc:
                import asyncio

                asyncio.run(connector._get("/user"))
        assert exc.value.error_type == expected


def test_github_execute_action_returns_structured_auth_error():
    connector = GitHubConnector({"tool_id": "github"})
    before = CONNECTOR_ERRORS_TOTAL.labels(
        connector="github", error_type="auth_failed"
    )._value.get()

    with patch.object(
        connector,
        "list_pull_requests",
        AsyncMock(
            side_effect=GitHubAPIError("auth_failed", "Invalid or missing token", 401)
        ),
    ):
        import asyncio

        result = asyncio.run(
            connector.execute_action(
                "list_pull_requests", {"repo": "org/repo"}
            )
        )

    assert result == {
        "ok": False,
        "tool": "github",
        "action": "list_pull_requests",
        "error": {"type": "auth_failed", "message": "Invalid or missing token"},
    }
    assert (
        CONNECTOR_ERRORS_TOTAL.labels(
            connector="github", error_type="auth_failed"
        )._value.get()
        == before + 1
    )


def test_webhook_signature_hmac_roundtrip():
    os.environ["GITHUB_WEBHOOK_SECRET"] = "super-secret"
    payload = b'{"action":"opened"}'
    signature = "sha256=" + hmac.new(
        b"super-secret", payload, hashlib.sha256
    ).hexdigest()
    assert verify_webhook_signature("github", payload, signature) is True
    assert verify_webhook_signature("github", payload, "sha256=deadbeef") is False


def test_require_valid_signature_rejects_missing_secret_outside_dev(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    with pytest.raises(HTTPException) as exc:
        require_valid_signature("github", b"{}", {})
    assert exc.value.status_code == 500
    assert "Webhook secret not configured" in exc.value.detail


def test_require_valid_signature_allows_missing_secret_in_dev(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    require_valid_signature("github", b"{}", {})


def test_github_ping_action_uses_rate_limit():
    connector = GitHubConnector({"tool_id": "github", "token": "t"})

    class FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"resources": {"core": {"remaining": 5000}}}

    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=None)
    fake_client.get = AsyncMock(return_value=FakeResp())
    with patch(
        "backend.connectors.github_connector.httpx.AsyncClient",
        return_value=fake_client,
    ):
        import asyncio

        result = asyncio.run(connector.execute_action("ping", {}))

    assert result["ok"] is True
    assert result["tool"] == "github"
    assert result["action"] == "ping"
    assert "resources" in (result.get("result") or {})
    fake_client.get.assert_awaited()
    called_url = fake_client.get.await_args.args[0]
    assert called_url.endswith("/rate_limit")


def test_github_probe_uses_tool_accounts(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    async def fake_execute(action, params):
        assert action == "ping"
        return {"ok": True, "tool": "github", "action": action, "result": {"ok": True}}

    with patch(
        "backend.connectors.github_connector.GitHubConnector.execute_action",
        new=AsyncMock(side_effect=fake_execute),
    ):
        from backend.health import _sync_github_probe

        result = _sync_github_probe(
            [
                {
                    "tool_id": "github",
                    "account_name": "prod-gh",
                    "credentials_vault_ref": "ghp_test",
                    "status": "connected",
                }
            ]
        )

    assert result["status"] == "healthy"
    assert result["configured"] is True
    assert result["account_name"] == "prod-gh"
    assert result.get("latency_ms") is not None


def test_tool_accounts_probe_includes_connector_statuses():
    summary = _sync_tool_accounts_probe(tool_accounts=[])
    assert summary["total"] == 5
    assert summary["tool_account_count"] == 0
    assert set(summary["connectors"]) == {
        "github",
        "jira",
        "aws",
        "kubernetes",
        "pagerduty",
    }
    for name, row in summary["connectors"].items():
        assert "status" in row
        assert "message" in row
        assert "configured" in row
        assert "latency_ms" in row


def test_platform_context_dev_helpers(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    assert PlatformContext.is_dev_environment() is False
    monkeypatch.setenv("ENV", "test")
    assert PlatformContext.is_dev_environment() is True
    ctx = PlatformContext(environment="development")
    assert ctx.is_dev() is True
    assert ctx.is_production() is False


def test_health_full_includes_connectors(client, admin_token):
    response = client.get(
        "/api/health/full",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "connectors" in data
    assert "github" in data["connectors"]
    assert "tools" in data
    assert "connectors" in data["tools"]
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
    assert "performance" in data
    assert "slow_queries" in data["performance"]
    assert "dependencies" in data
    assert "vulnerabilities" in data["dependencies"]


def test_build_tuning_recommendations_from_probes():
    from backend.health import build_tuning_recommendations

    recs = build_tuning_recommendations(
        {
            "performance": {
                "available": True,
                "slow_queries": [
                    {
                        "query": "SELECT * FROM big_table WHERE id = $1",
                        "mean_exec_time": 1200.0,
                        "calls": 40,
                        "total_exec_time": 48000.0,
                    }
                ],
            },
            "dependencies": {
                "vulnerability_count": 1,
                "vulnerabilities": [
                    {
                        "package": "demo",
                        "version": "0.1",
                        "vulnerability_id": "PYSEC-1",
                        "severity": "high",
                    }
                ],
            },
            "tools": {"degraded": ["github"]},
            "database": {"latency_ms": 10},
            "redis": {"status": "healthy"},
        }
    )
    cats = {r["category"] for r in recs}
    assert "performance" in cats
    assert "dependencies" in cats
    assert "connectors" in cats


def test_dashboard_health_recommendations(client, admin_token):
    response = client.get(
        "/api/dashboard/health-recommendations",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)
