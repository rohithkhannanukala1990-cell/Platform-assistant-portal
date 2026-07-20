"""SSO / SAML + Google OAuth tests for backend.routers.sso."""

from __future__ import annotations

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from backend.main import app

# Module-level client (tests prefer the lifespan-aware `client` fixture from conftest).
client = TestClient(app)

IDP_METADATA_XML = """<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata">
  <IDPSSODescriptor>
    <SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="https://idp.example.com/login"/>
  </IDPSSODescriptor>
</EntityDescriptor>"""


@respx.mock
def test_saml_login_redirects_to_sso_url(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    metadata_url = "https://idp.example.com/metadata"
    monkeypatch.setenv("SAML_IDP_METADATA_URL", metadata_url)

    respx.get(metadata_url).mock(
        return_value=httpx.Response(200, text=IDP_METADATA_XML)
    )

    response = client.get("/api/auth/sso/saml/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "https://idp.example.com/login"


def test_saml_acs_rejects_invalid_signature(client: TestClient):
    response = client.post(
        "/api/auth/sso/saml/acs",
        data={"SAMLResponse": "FAKEINVALIDBASE64DATA"},
        follow_redirects=False,
    )
    assert response.status_code == 401


@respx.mock
def test_google_oauth_callback_success(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost/cb")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:5173")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "fake-token", "token_type": "Bearer"},
        )
    )
    respx.get("https://www.googleapis.com/oauth2/v3/userinfo").mock(
        return_value=httpx.Response(
            200,
            json={"email": "user@example.com", "name": "Test User"},
        )
    )

    # Router path is /api/auth/oauth/google/callback (prefix /api/auth).
    response = client.get(
        "/api/auth/oauth/google/callback?code=authcode123",
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    assert "token=" in response.headers["location"]


@respx.mock
def test_google_oauth_callback_token_exchange_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "http://localhost/cb")

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(400, json={"error": "invalid_grant"})
    )

    response = client.get("/api/auth/oauth/google/callback?code=badcode")
    assert response.status_code == 502
