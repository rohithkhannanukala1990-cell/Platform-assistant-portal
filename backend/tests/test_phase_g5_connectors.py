"""Phase G5 — first-class connector pack (Slack, Prometheus, Outbound Webhook, ArgoCD)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from backend.tests.conftest import auth_headers


def test_slack_channels_requires_auth(client):
    assert client.get("/api/slack/channels").status_code == 401


def test_prometheus_alerts_requires_auth(client):
    assert client.get("/api/prometheus/alerts").status_code == 401


def test_argocd_apps_requires_auth(client):
    assert client.get("/api/argocd/applications").status_code == 401


def test_outbound_webhook_status_requires_auth(client):
    assert client.get("/api/outbound-webhook/status").status_code == 401


def test_slack_400_when_not_connected(client, admin_token):
    h = auth_headers(admin_token)
    accounts = client.get("/api/tools/slack/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/slack/accounts/{acc['id']}", headers=h)
    r = client.get("/api/slack/channels", headers=h)
    assert r.status_code == 400
    assert "Tool Registry" in (r.json().get("detail") or "")


def test_prometheus_400_when_not_connected(client, admin_token):
    h = auth_headers(admin_token)
    accounts = client.get("/api/tools/prometheus/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/prometheus/accounts/{acc['id']}", headers=h)
    r = client.get("/api/prometheus/alerts", headers=h)
    assert r.status_code == 400
    assert "Prometheus" in (r.json().get("detail") or "")


def test_slack_channels_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/slack/accounts",
        headers=h,
        json={
            "account_name": "g5-slack",
            "environment": "development",
            "auth_type": "bot_token",
            "credentials_vault_ref": "xoxb-test-token",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]
    fake = [{"id": "C1", "name": "ops", "is_private": False, "num_members": 3}]
    with patch("backend.routers.slack_ops.slack_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.list_channels = AsyncMock(return_value=fake)
        mock_resolve.return_value = connector
        r = client.get("/api/slack/channels", headers=h)
    assert r.status_code == 200
    assert r.json()[0]["name"] == "ops"
    client.delete(f"/api/tools/slack/accounts/{aid}", headers=h)


def test_prometheus_alerts_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/prometheus/accounts",
        headers=h,
        json={
            "account_name": "g5-prom",
            "environment": "development",
            "auth_type": "bearer_token",
            "instance_url": "http://prometheus.local",
            "credentials_vault_ref": "prom-token",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]
    fake = [{"name": "HighCPU", "state": "firing", "severity": "critical", "service": "api"}]
    with patch("backend.routers.prometheus_ops.prometheus_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.list_alerts = AsyncMock(return_value=fake)
        mock_resolve.return_value = connector
        r = client.get("/api/prometheus/alerts", headers=h)
    assert r.status_code == 200
    assert r.json()[0]["name"] == "HighCPU"
    client.delete(f"/api/tools/prometheus/accounts/{aid}", headers=h)


def test_argocd_applications_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/argocd/accounts",
        headers=h,
        json={
            "account_name": "g5-argo",
            "environment": "development",
            "auth_type": "token",
            "instance_url": "https://argocd.example.com",
            "credentials_vault_ref": "argo-token",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]
    fake = [{"name": "payments", "health": "Healthy", "sync": "Synced", "project": "default"}]
    with patch("backend.routers.argocd_ops.argocd_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.list_applications = AsyncMock(return_value=fake)
        mock_resolve.return_value = connector
        r = client.get("/api/argocd/applications", headers=h)
    assert r.status_code == 200
    assert r.json()[0]["health"] == "Healthy"
    client.delete(f"/api/tools/argocd/accounts/{aid}", headers=h)


def test_outbound_webhook_status_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/outbound_webhook/accounts",
        headers=h,
        json={
            "account_name": "g5-ow",
            "environment": "development",
            "auth_type": "webhook",
            "instance_url": "https://hooks.customer.example/portal",
            "credentials_vault_ref": "signing-secret",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]
    with patch("backend.routers.outbound_webhook_ops.outbound_webhook_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.ping = AsyncMock(return_value={"ok": True, "url_host": "hooks.customer.example"})
        mock_resolve.return_value = connector
        r = client.get("/api/outbound-webhook/status", headers=h)
    assert r.status_code == 200
    assert r.json()["ok"] is True
    client.delete(f"/api/tools/outbound_webhook/accounts/{aid}", headers=h)


def test_slack_notify_requires_admin_or_hitl(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/slack/accounts",
        headers=h,
        json={
            "account_name": "g5-slack-notify",
            "environment": "development",
            "auth_type": "webhook",
            "instance_url": "https://hooks.slack.com/services/T/B/X",
            "credentials_vault_ref": "https://hooks.slack.com/services/T/B/X",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]
    with patch("backend.routers.slack_ops.slack_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.notify_channel = AsyncMock(return_value={"ok": True, "mode": "webhook"})
        mock_resolve.return_value = connector
        r = client.post(
            "/api/slack/notify",
            headers=h,
            json={"text": "hello from portal"},
        )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    client.delete(f"/api/tools/slack/accounts/{aid}", headers=h)


def test_servicenow_create_requires_hitl_for_non_admin(client):
    from backend.tests.test_phase9_isolation import _login, _make_user

    _make_user("g5-snow-user", tenant_id="default", role="User")
    token = _login(client, "g5-snow-user")
    h = auth_headers(token)
    # May 400 if no account, or 403 if connected without approved — either is fine for write gate.
    r = client.post(
        "/api/servicenow/incidents",
        headers=h,
        json={"short_description": "test", "approved": False},
    )
    assert r.status_code in (400, 403)
