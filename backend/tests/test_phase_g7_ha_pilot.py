"""Phase G7 — HA readiness (db+redis) + production compose / config defaults."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from backend.services import readiness as readiness_mod
from backend.services.readiness import (
    evaluate_readiness,
    production_safety_snapshot,
    uses_sqlite,
    workspace_isolation_enforced,
)


ROOT = Path(__file__).resolve().parents[2]
PROD_COMPOSE = ROOT / "deploy" / "docker-compose.prod.yml"


def test_health_live_and_ready_endpoints(client):
    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json().get("status") == "ok"

    # Pytest SQLite stack: Redis optional → ready when DB is up
    ready = client.get("/health/ready")
    assert ready.status_code == 200, ready.text
    body = ready.json()
    assert body.get("status") == "ready"
    assert "database" in body.get("checks", {})
    assert "redis" in body.get("checks", {})
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] in {"ok", "skipped"}

    alias = client.get("/ready")
    assert alias.status_code == 200
    assert alias.json().get("status") == "ready"


def test_evaluate_readiness_fails_when_db_down(monkeypatch):
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("ENV", "test")

    with patch.object(
        readiness_mod,
        "check_database",
        return_value={"status": "error", "detail": "database_unavailable"},
    ):
        payload = evaluate_readiness(require_redis=False)
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "error"


def test_evaluate_readiness_requires_redis_when_url_set(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/aiops")

    with (
        patch.object(
            readiness_mod,
            "check_database",
            return_value={"status": "ok", "detail": "database_reachable"},
        ),
        patch.object(
            readiness_mod,
            "check_redis",
            return_value={"status": "error", "detail": "redis_unavailable", "required": True},
        ),
    ):
        payload = evaluate_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["redis"]["status"] == "error"

    with (
        patch.object(
            readiness_mod,
            "check_database",
            return_value={"status": "ok", "detail": "database_reachable"},
        ),
        patch.object(
            readiness_mod,
            "check_redis",
            return_value={"status": "ok", "detail": "redis_reachable", "required": True},
        ),
    ):
        ok = evaluate_readiness()
    assert ok["status"] == "ready"


def test_production_env_requires_redis_even_without_url(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with patch.object(
        readiness_mod,
        "check_database",
        return_value={"status": "ok", "detail": "database_reachable"},
    ):
        payload = evaluate_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["redis"]["detail"] == "redis_not_configured"


def test_config_defaults_helpers(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ENABLE_DEMO_DATA", "false")
    monkeypatch.setenv("ENFORCE_WORKSPACE_ISOLATION", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/aiops")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://:secret@redis:6379/0")

    assert uses_sqlite() is False
    assert workspace_isolation_enforced() is True
    snap = production_safety_snapshot()
    assert snap["enable_demo_data"] is False
    assert snap["enforce_workspace_isolation"] is True
    assert snap["ok_for_pilot"] is True

    monkeypatch.setenv("ENABLE_DEMO_DATA", "true")
    assert production_safety_snapshot()["ok_for_pilot"] is False


def test_prod_compose_ha_baseline_defaults():
    assert PROD_COMPOSE.is_file(), f"missing {PROD_COMPOSE}"
    raw = PROD_COMPOSE.read_text(encoding="utf-8")

    for svc in (
        "postgres:",
        "redis:",
        "api_1:",
        "api_2:",
        "celery_worker_1:",
        "celery_worker_2:",
        "nginx:",
    ):
        assert svc in raw, f"expected service {svc}"

    assert 'ENABLE_DEMO_DATA: "false"' in raw
    assert 'ENFORCE_WORKSPACE_ISOLATION: "true"' in raw
    assert "ENV: production" in raw
    assert "DATABASE_URL: postgresql://" in raw
    assert "sqlite:///" not in raw.lower()

    nginx_conf = (ROOT / "deploy" / "nginx.prod.conf").read_text(encoding="utf-8")
    assert "api_1:8000" in nginx_conf
    assert "api_2:8000" in nginx_conf
    assert "/health/ready" in nginx_conf
