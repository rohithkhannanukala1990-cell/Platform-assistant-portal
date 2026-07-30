"""Pytest fixtures: isolate DB and run FastAPI lifespan (creates tables + seed admin)."""

import os
from pathlib import Path

# Must run before importing backend.* (database URL is read at import time).
_test_db = Path(__file__).resolve().parent.parent / "test_pytest.db"
if _test_db.exists():
    try:
        _test_db.unlink(missing_ok=True)
    except PermissionError:
        # Windows: prior pytest/IDE may still hold the file — use a unique DB path.
        _test_db = Path(__file__).resolve().parent.parent / f"test_pytest_{os.getpid()}.db"

os.environ["DATABASE_URL"] = f"sqlite:///{_test_db.as_posix()}"
os.environ["SKIP_BACKGROUND_SCHEDULER"] = "1"
os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "pytest-jwt-secret-not-for-production")
os.environ.setdefault("LLM_MOCK", "1")
os.environ.setdefault("LLM_DEFAULT_PROVIDER", "openai")
os.environ.setdefault("LLM_DEFAULT_MODEL", "gpt-4o-mini")
# Match docker-compose default so seed_default_admin() hashes the same password tests use.
os.environ.setdefault("DEFAULT_ADMIN_USERNAME", "admin")
os.environ.setdefault("DEFAULT_ADMIN_PASSWORD", "Admin123!")

# SSO / SAML / Google OAuth defaults for backend.tests.test_sso
os.environ.setdefault("SAML_IDP_METADATA_URL", "https://idp.example.com/metadata")
os.environ.setdefault("SAML_SP_ENTITY_ID", "https://sp.example.com/metadata")
os.environ.setdefault("SAML_SP_ACS_URL", "https://sp.example.com/acs")
os.environ.setdefault("SAML_IDP_ENTITY_ID", "https://idp.example.com/metadata")
os.environ.setdefault("SAML_IDP_SSO_URL", "https://idp.example.com/login")
os.environ.setdefault(
    "SAML_IDP_CERT",
    "MIIDXTCCAkWgAwIBAgIJAJC1HiInMyklMA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV"
    "BAYTAkFVMRMwEQYDVQQIDApTb21lLVN0YXRlMSEwHwYDVQQKDBhJbnRlcm5ldCBX"
    "aWRnaXRzIFB0eSBMdGQwHhcNMTYxMTExMTgxNjM0WhcNMTcxMTExMTgxNjM0WjBF"
    "MQswCQYDVQQGEwJBVTETMBEGA1UECAwKU29tZS1TdGF0ZTEhMB8GA1UECgwYSW50"
    "ZXJuZXQgV2lkZ2l0cyBQdHkgTHRkMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIB"
    "CgKCAQEAuopExampleCertForPytestOnlyNotRealAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "wIDAQABMA0GCSqGSIb3DQEBCwUAA4IBAQCexample",
)
os.environ.setdefault("GOOGLE_CLIENT_ID", "test")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost/cb")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("ADMIN_EMAILS", "")

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
