"""Pytest fixtures: isolate DB and run FastAPI lifespan (creates tables + seed admin)."""

import os
from pathlib import Path

# Must run before importing backend.* (database URL is read at import time).
_test_db = Path(__file__).resolve().parent.parent / "test_pytest.db"
if _test_db.exists():
    _test_db.unlink(missing_ok=True)

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.as_posix()}"
os.environ.setdefault("JWT_SECRET_KEY", "pytest-jwt-secret-not-for-production")
# Match docker-compose default so seed_default_admin() hashes the same password tests use.
os.environ.setdefault("DEFAULT_ADMIN_USERNAME", "admin")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "Admin123!")

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="module")
def client():
    """Lifespan startup seeds DB tables and default admin (required for /auth/login)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client):
    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "Admin123!"},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
