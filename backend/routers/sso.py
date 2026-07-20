"""SSO / SAML + Google OAuth integration stubs."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from sqlmodel import Session, select

from ..auth import User, create_access_token, hash_password
from ..database import engine

router = APIRouter(prefix="/api/auth", tags=["sso"])

ADMIN_EMAILS = {
    e.strip()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


def _get_or_create_sso_user(email: str, role: str) -> User:
    """Look up a user by email; create one if not found."""
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if user:
            return user
        user = User(
            username=email,
            email=email,
            hashed_password=hash_password(os.urandom(32).hex()),
            role=role.capitalize(),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


# ── SAML ──────────────────────────────────────────────────────────────────────

@router.get("/sso/saml/metadata")
async def saml_metadata():
    """Returns SP metadata XML for IdP configuration."""
    entity_id = os.getenv("SAML_SP_ENTITY_ID", "")
    acs_url = os.getenv("SAML_SP_ACS_URL", "")
    xml = f"""<?xml version="1.0"?>
<EntityDescriptor entityID="{entity_id}"
  xmlns="urn:oasis:names:tc:SAML:2.0:metadata">
  <SPSSODescriptor>
    <AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="{acs_url}" index="1"/>
  </SPSSODescriptor>
</EntityDescriptor>"""
    return Response(content=xml, media_type="application/xml")


@router.get("/sso/saml/login")
async def saml_login():
    """Fetch IdP metadata and redirect to the HTTP-Redirect SSO URL."""
    try:
        idp_url = os.getenv("SAML_IDP_METADATA_URL", "")
        if not idp_url:
            raise HTTPException(400, "SAML not configured")

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(idp_url)

        if response.status_code != 200:
            raise HTTPException(502, "IdP metadata unavailable")

        root = ET.fromstring(response.text)
        sso_url = None
        for el in root.findall(
            ".//{urn:oasis:names:tc:SAML:2.0:metadata}SingleSignOnService"
        ):
            binding = el.get("Binding") or ""
            if "HTTP-Redirect" in binding:
                sso_url = el.get("Location")
                break

        if not sso_url:
            raise HTTPException(
                502, "No HTTP-Redirect binding found in IdP metadata"
            )

        return RedirectResponse(sso_url)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, str(e))


@router.post("/sso/saml/acs")
async def saml_acs(request: Request):
    """Assertion Consumer Service — validates SAML response via python3-saml."""
    settings = {
        "sp": {
            "entityId": os.getenv("SAML_SP_ENTITY_ID", ""),
            "assertionConsumerService": {
                "url": os.getenv("SAML_SP_ACS_URL", ""),
            },
            "x509cert": os.getenv("SAML_SP_CERT", ""),
            "privateKey": os.getenv("SAML_SP_KEY", ""),
        },
        "idp": {
            "entityId": os.getenv("SAML_IDP_ENTITY_ID", ""),
            "singleSignOnService": {
                "url": os.getenv("SAML_IDP_SSO_URL", ""),
            },
            "x509cert": os.getenv("SAML_IDP_CERT", ""),
        },
    }

    form_data = await request.form()
    req = {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.headers.get("host"),
        "script_name": request.url.path,
        "server_port": str(request.url.port or 443),
        "get_data": dict(request.query_params),
        "post_data": dict(form_data),
    }

    auth = OneLogin_Saml2_Auth(req, settings)
    auth.process_response()

    if auth.get_errors() or not auth.is_authenticated():
        raise HTTPException(status_code=401, detail=str(auth.get_errors()))

    email = auth.get_nameid()
    role = "Admin" if email in ADMIN_EMAILS else "User"
    user = _get_or_create_sso_user(email=email, role=role)
    token = create_access_token(username=user.username, role=user.role)
    return RedirectResponse(f"{os.getenv('FRONTEND_URL')}/auth/callback#token={token}")


# ── Google OAuth2 stub ────────────────────────────────────────────────────────

@router.get("/oauth/google")
async def google_oauth_start():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    redirect = os.getenv("SAML_SP_ACS_URL", "").replace(
        "saml/acs", "oauth/google/callback"
    )
    if not client_id:
        raise HTTPException(400, "Google OAuth not configured")
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect}"
        "&response_type=code"
        "&scope=openid%20email%20profile"
    )
    return RedirectResponse(url)


@router.get("/oauth/google/callback")
async def google_oauth_callback(request: Request):
    """Complete Google OAuth2 authorization-code flow and issue a JWT."""
    try:
        code = request.query_params.get("code")
        if not code:
            raise HTTPException(400, "Missing authorization code")

        async with httpx.AsyncClient(timeout=15) as client:
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
                    "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI", ""),
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise HTTPException(
                    502,
                    f"Google token exchange failed: {token_response.text}",
                )
            access_token = token_response.json()["access_token"]

            userinfo_response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code != 200:
                raise HTTPException(502, "Failed to fetch Google user info")

            email = userinfo_response.json().get("email")
            if not email:
                raise HTTPException(400, "Google account has no email address")

        admin_emails = os.getenv("ADMIN_EMAILS", "").split(",")
        role = (
            "Admin"
            if email.strip() in [e.strip() for e in admin_emails]
            else "User"
        )
        user = _get_or_create_sso_user(email=email, role=role)
        token = create_access_token(username=user.username, role=role)
        return RedirectResponse(
            f"{os.getenv('FRONTEND_URL')}/auth/callback#token={token}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))
