"""Phase 2 authentication, MFA, RBAC, and role-safety tests."""

from __future__ import annotations

import pyotp
from sqlmodel import Session, select

from backend.auth import (
    AuditLog,
    User,
    create_access_token,
    hash_password,
    normalize_role,
    sync_user_rbac_role,
)
from backend.database import engine


def _create_user(
    username: str,
    *,
    role: str = "User",
    password: str = "Password123!",
    mfa_secret: str | None = None,
) -> User:
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing:
            return existing
        user = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password(password),
            role=normalize_role(role),
            is_active=True,
            mfa_enabled=bool(mfa_secret),
            mfa_secret=mfa_secret,
        )
        session.add(user)
        session.flush()
        sync_user_rbac_role(session, user, granted_by="pytest")
        session.commit()
        session.refresh(user)
        return user


def _headers_for(user: User) -> dict[str, str]:
    token = create_access_token(user.username, normalize_role(user.role))
    return {"Authorization": f"Bearer {token}"}


def test_mfa_login_requires_code_and_rejects_invalid_code(client):
    secret = pyotp.random_base32()
    user = _create_user("mfa-user", mfa_secret=secret)

    missing = client.post(
        "/auth/login",
        data={"username": user.username, "password": "Password123!"},
    )
    assert missing.status_code == 401
    assert missing.json()["detail"] == "MFA code required"

    invalid = client.post(
        "/auth/login",
        data={
            "username": user.username,
            "password": "Password123!",
            "totp_code": "000000",
        },
    )
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid MFA code"

    with Session(engine) as session:
        audit = session.exec(
            select(AuditLog)
            .where(
                AuditLog.actor == user.username,
                AuditLog.event_type == "LOGIN_FAILED_MFA",
            )
            .order_by(AuditLog.timestamp.desc())
        ).first()
    assert audit is not None
    assert audit.detail == "Invalid MFA code"


def test_mfa_login_accepts_valid_totp(client):
    secret = pyotp.random_base32()
    user = _create_user("mfa-valid-user", mfa_secret=secret)

    response = client.post(
        "/auth/login",
        data={
            "username": user.username,
            "password": "Password123!",
            "totp_code": pyotp.TOTP(secret).now(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


def test_admin_header_no_longer_bypasses_authentication(client):
    response = client.post(
        "/api/catalog",
        headers={"X-User-Id": "admin"},
        json={
            "name": "header-bypass-attempt",
            "kind": "Service",
            "lifecycle": "production",
            "owner_team": "security",
        },
    )
    assert response.status_code == 401


def test_readonly_user_cannot_write_catalog_or_run_golden_path(client):
    viewer = _create_user("readonly-user", role="ReadOnly")
    headers = _headers_for(viewer)

    catalog = client.post(
        "/api/catalog",
        headers=headers,
        json={
            "name": "forbidden-service",
            "kind": "Service",
            "lifecycle": "production",
            "owner_team": "security",
        },
    )
    run = client.post(
        "/api/golden-paths/1/run",
        headers=headers,
        json={"inputs": {}},
    )

    assert catalog.status_code == 403
    assert run.status_code == 403


def test_role_normalization_uses_canonical_backend_roles():
    assert normalize_role("Admin") == "Admin"
    assert normalize_role("super-admin") == "Admin"
    assert normalize_role("Operator") == "User"
    assert normalize_role("Developer") == "User"
    assert normalize_role("Viewer") == "ReadOnly"
    assert normalize_role("ReadOnly") == "ReadOnly"
