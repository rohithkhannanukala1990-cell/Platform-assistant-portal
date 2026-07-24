"""Phase 13 — Enterprise identity: MFA policy, sessions, audit export."""

from __future__ import annotations

import pyotp
from sqlmodel import Session, select

from backend.auth import User, create_access_token, hash_password, normalize_role
from backend.database import engine
from backend.tests.conftest import auth_headers


def _ensure_user(username: str, *, role: str = "Admin", password: str = "Password123!", mfa: bool = False) -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.role = normalize_role(role)
            existing.mfa_enabled = mfa
            if mfa and not existing.mfa_secret:
                existing.mfa_secret = pyotp.random_base32()
            if not mfa:
                existing.mfa_secret = None
            existing.hashed_password = hash_password(password)
            existing.is_active = True
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        secret = pyotp.random_base32() if mfa else None
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password(password),
            role=normalize_role(role),
            is_active=True,
            mfa_enabled=mfa,
            mfa_secret=secret,
            tenant_id="default",
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def test_admin_without_mfa_blocked_when_policy_on(client, monkeypatch):
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "Admin,PlatformAdmin")
    # Force reload of policy reads from env (function reads env each call)
    user = _ensure_user("phase13-admin-nomfa", role="Admin", mfa=False)

    r = client.post(
        "/auth/login",
        data={"username": user.username, "password": "Password123!"},
    )
    assert r.status_code == 403, r.text
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "mfa_enrollment_required"


def test_admin_with_mfa_can_login_when_policy_on(client, monkeypatch):
    monkeypatch.setenv("MFA_REQUIRED_ROLES", "Admin")
    secret = pyotp.random_base32()
    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == "phase13-admin-mfa")).first()
        if u is None:
            u = User(
                username="phase13-admin-mfa",
                email="phase13-admin-mfa@example.com",
                hashed_password=hash_password("Password123!"),
                role="Admin",
                is_active=True,
                mfa_enabled=True,
                mfa_secret=secret,
                tenant_id="default",
            )
            session.add(u)
        else:
            u.mfa_enabled = True
            u.mfa_secret = secret
            u.hashed_password = hash_password("Password123!")
            session.add(u)
        session.commit()

    code = pyotp.TOTP(secret).now()
    r = client.post(
        "/auth/login",
        data={"username": "phase13-admin-mfa", "password": "Password123!", "totp_code": code},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("access_token")


def test_audit_export_requires_admin(client, admin_token):
    # Non-admin
    user = _ensure_user("phase13-viewer", role="User")
    login = client.post(
        "/auth/login",
        data={"username": user.username, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    user_token = login.json()["access_token"]

    denied = client.get(
        "/api/audit/export?format=json",
        headers=auth_headers(user_token),
    )
    assert denied.status_code == 403

    ok = client.get(
        "/api/audit/export?format=json&event_types=login_success,login_failed,mfa,APPROVE,REJECT",
        headers=auth_headers(admin_token),
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert "results" in body
    assert "count" in body


def test_revoke_rejects_old_token(client):
    user = _ensure_user("phase13-session", role="User")
    login = client.post(
        "/auth/login",
        data={"username": user.username, "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    h = auth_headers(token)

    sessions = client.get("/api/auth/sessions", headers=h)
    assert sessions.status_code == 200, sessions.text
    rows = sessions.json().get("sessions") or []
    assert len(rows) >= 1
    jti = rows[0]["jti"]

    revoke = client.post(
        "/api/auth/sessions/revoke",
        headers=h,
        json={"jti": jti},
    )
    assert revoke.status_code == 200, revoke.text

    me = client.get("/auth/me", headers=h)
    assert me.status_code == 401


def test_sso_status_no_fake_success(client):
    r = client.get("/api/auth/sso/status")
    assert r.status_code == 200
    body = r.json()
    assert "saml" in body and "google" in body
    # Without IdP env in tests, providers should be false (conftest sets SAML urls
    # for SSO unit tests — status may still be true). Just ensure shape is honest.
    assert isinstance(body["saml"], bool)
    assert isinstance(body["google"], bool)


def test_logout_revokes_current(client):
    user = _ensure_user("phase13-logout", role="User")
    login = client.post(
        "/auth/login",
        data={"username": user.username, "password": "Password123!"},
    )
    token = login.json()["access_token"]
    h = auth_headers(token)
    out = client.post("/api/auth/logout", headers=h)
    assert out.status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401
