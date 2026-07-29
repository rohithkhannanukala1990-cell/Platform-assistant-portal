"""Phase 17 — HA/scale: Redis rate limits, indexes, pagination defaults."""

from __future__ import annotations

from sqlmodel import Session, text

from backend.database import engine
from backend.rate_limit import limiter
from backend.services.pagination import clamp_page
from backend.services.redis_url import redis_url
from backend.tests.conftest import auth_headers


def test_clamp_page_defaults():
    page, size, offset = clamp_page()
    assert page == 1 and size == 50 and offset == 0
    page, size, offset = clamp_page(3, 25)
    assert page == 3 and size == 25 and offset == 50
    _, size, _ = clamp_page(1, 999)
    assert size == 100


def test_redis_url_prefers_ratelimit_then_celery(monkeypatch):
    monkeypatch.delenv("RATELIMIT_STORAGE_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert redis_url() is None
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    assert redis_url() == "redis://redis:6379/0"
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://celery:6379/0")
    assert redis_url() == "redis://celery:6379/0"
    monkeypatch.setenv("RATELIMIT_STORAGE_URL", "redis://rl:6379/1")
    assert redis_url() == "redis://rl:6379/1"


def test_rate_limiter_uses_redis_storage_when_url_set(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from backend import rate_limit as rl

    rebuilt = rl._build_limiter()
    assert rebuilt._storage_uri == "redis://localhost:6379/0"
    assert "redis" in type(rebuilt._storage).__module__.lower()
    assert limiter is not None


def test_scale_indexes_exist(client):
    # Lifespan (via client) runs create_db_and_tables + _migrate/_ensure_scale_indexes
    with Session(engine) as session:
        rows = session.exec(text("PRAGMA index_list('incident')")).all()
        names = {r[1] for r in rows}
        assert "ix_incident_tenant_id" in names
        assert "ix_incident_timestamp" in names
        rows_wd = session.exec(text("PRAGMA index_list('webhook_delivery')")).all()
        wd_names = {r[1] for r in rows_wd}
        assert "ix_webhook_delivery_delivery_id" in wd_names or any(
            "webhook_delivery" in n for n in wd_names
        )


def test_incidents_list_paginated(client, admin_token):
    h = auth_headers(admin_token)
    r = client.get("/api/incidents?page=1&page_size=10", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) <= 10


def test_notifications_list_paginated(client, admin_token):
    h = auth_headers(admin_token)
    r = client.get("/api/notifications?page=1&page_size=5", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) <= 5


def test_catalog_list_paginated(client, admin_token):
    h = auth_headers(admin_token)
    r = client.get("/api/catalog?page=1&page_size=5", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert len(r.json()) <= 5
