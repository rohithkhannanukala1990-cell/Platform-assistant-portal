"""Phase P1 — production blockers: SSL, SSRF, demo gates, executor, weak admin."""

from __future__ import annotations

import asyncio

import pytest

from backend.auth import WeakAdminPasswordError, seed_default_admin
from backend.connectors.argocd_connector import ArgoCDConnector
from backend.connectors.outbound_webhook_connector import OutboundWebhookConnector
from backend.executor.safe_executor import safe_executor
from backend.services.command_policy import evaluate_command
from backend.services.ssrf import assert_safe_outbound_url
from backend.tasks import monitor_cicd_pipelines


def test_argocd_tls_verify_default_secure(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    c = ArgoCDConnector({"instance_url": "https://argocd.example", "token": "t"})
    assert c._verify_tls() is True


def test_argocd_tls_never_insecure_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    c = ArgoCDConnector(
        {
            "instance_url": "https://argocd.example",
            "token": "t",
            "insecure_skip_tls_verify": "true",
        }
    )
    assert c._verify_tls() is True


def test_argocd_tls_opt_in_insecure_non_prod(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    c = ArgoCDConnector(
        {
            "instance_url": "https://argocd.example",
            "token": "t",
            "insecure_skip_tls_verify": "true",
        }
    )
    assert c._verify_tls() is False


def test_ssrf_blocks_metadata_and_file():
    with pytest.raises(ValueError, match="blocked"):
        assert_safe_outbound_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(ValueError, match="scheme"):
        assert_safe_outbound_url("file:///etc/passwd")
    with pytest.raises(ValueError, match="blocked"):
        assert_safe_outbound_url("http://127.0.0.1:8080/hooks")


def test_outbound_webhook_ssrf_blocked_host():
    conn = OutboundWebhookConnector(
        {"webhook_url": "http://169.254.169.254/hook", "token": "s"}
    )
    result = asyncio.run(conn.deliver("test", {"x": 1}))
    assert result.get("ok") is False
    assert "ssrf" in str(result.get("error", "")).lower()


def test_demo_off_monitor_cicd_no_fake_incidents(monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_DATA", "false")
    monkeypatch.setenv("ENV", "production")
    out = monitor_cicd_pipelines.run()
    assert out.get("skipped") is True
    assert out.get("reason") == "demo_data_disabled"


def test_executor_refuses_without_approval_in_production(client):
    out = asyncio.run(
        safe_executor.execute(
            ["echo p1-safe-check"],
            incident_id=0,
            approved_by="tester",
            context={
                "role": "Admin",
                "environment": "production",
                "tool": "shell",
                "tenant_id": "default",
                "approved": False,
            },
        )
    )
    assert out.get("success") is False
    assert out.get("requires_approval") is True or out.get("policy_effect") in {
        "require_approval",
        "deny",
    }


def test_policy_default_require_approval_in_production(client):
    decision = evaluate_command(
        "curl -X POST http://example.internal/reset",
        role="Admin",
        environment="production",
    )
    assert decision.effect == "require_approval"
    assert decision.safe_for_auto is False


def test_weak_admin_password_rejected_in_production(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "change_me")
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "prod-admin-weak-test")
    with pytest.raises(WeakAdminPasswordError):
        seed_default_admin()


def test_cors_strips_wildcard_and_fail_closed_production(monkeypatch):
    from backend import main as main_mod

    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com,*")
    origins = main_mod._cors_allow_origins()
    assert "*" not in origins
    assert "https://app.example.com" in origins

    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    assert main_mod._cors_allow_origins() == []


def test_prod_compose_requires_secrets_fail_fast():
    """Empty SECRET_KEY / POSTGRES_PASSWORD must not silently interpolate."""
    from pathlib import Path

    prod = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "docker-compose.prod.yml"
    )
    raw = prod.read_text(encoding="utf-8")
    for var in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "SECRET_KEY",
        "SECRETS_ENCRYPTION_KEY",
        "DEFAULT_ADMIN_PASSWORD",
    ):
        assert f"${{{var}:?" in raw, f"{var} must use ${{VAR:?err}} fail-fast syntax"


def test_prod_compose_frontend_has_writable_tmpfs():
    """nginx:alpine on read_only rootfs needs tmpfs for /var/cache/nginx + /var/run."""
    from pathlib import Path

    raw = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")
    assert "/var/cache/nginx" in raw, "frontend must mount /var/cache/nginx as tmpfs"
    assert "/var/run" in raw, "frontend must mount /var/run as tmpfs"


def test_prod_compose_forwards_sso_and_webhook_env():
    """SAML / Google / webhook HMAC secrets must reach api containers."""
    from pathlib import Path

    raw = (
        Path(__file__).resolve().parents[2]
        / "deploy"
        / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")
    for key in (
        "SAML_IDP_METADATA_URL",
        "SAML_SP_ACS_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_REDIRECT_URI",
        "GITHUB_WEBHOOK_SECRET",
        "OPENAI_API_KEY",
    ):
        assert key in raw, f"prod compose must forward {key} to api containers"


def test_health_workflow_uses_pipefail():
    """Daily health check must alert on total outage (curl failure)."""
    from pathlib import Path

    raw = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "health.yml"
    ).read_text(encoding="utf-8")
    assert "pipefail" in raw
    # curl failure must fall through to critical
    assert 'STATUS="critical"' in raw or "STATUS=critical" in raw
