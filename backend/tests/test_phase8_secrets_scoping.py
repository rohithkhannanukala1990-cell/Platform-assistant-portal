"""Phase 8: secrets encrypt-at-rest + GitHub tool account scoping."""

from __future__ import annotations

import uuid

from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.database import Tool, ToolAccount
from backend.services.github_access import resolve_github_tool_account
from backend.services.secrets import decrypt_secret, encrypt_secret, reset_secret_box_for_tests
from backend.tests.conftest import auth_headers


def _ensure_github_tool(session: Session) -> None:
    if session.get(Tool, "github") is None:
        session.add(
            Tool(
                id="github",
                name="GitHub",
                category="source_control",
                description="GitHub",
            )
        )
        session.commit()


def _make_user(username: str) -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            return existing
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password("Password123!"),
            role="User",
            is_active=True,
            tenant_id="default",
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def test_encrypt_decrypt_roundtrip_with_key(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", key)
    reset_secret_box_for_tests()
    token = "ghp_phase8_roundtrip_secret"
    enc = encrypt_secret(token)
    assert enc != token
    assert decrypt_secret(enc) == token
    reset_secret_box_for_tests()


def test_user_b_does_not_resolve_user_a_github_account(client):
    user_a = _make_user("phase8-user-a")
    user_b = _make_user("phase8-user-b")
    with Session(engine) as session:
        _ensure_github_tool(session)
        acc_a = ToolAccount(
            id=str(uuid.uuid4()),
            tool_id="github",
            account_name="user-a-gh",
            environment="development",
            auth_type="pat",
            credentials_vault_ref=encrypt_secret("ghp_user_a_only"),
            is_active=1,
            created_by=user_a.username,
            owner_user_id=str(user_a.id),
            tenant_id="default",
        )
        session.add(acc_a)
        session.commit()
        aid = acc_a.id

        resolved_b = resolve_github_tool_account(session, user=user_b)
        assert resolved_b is None

        # Even with a hint to A's account, B must not get it
        resolved_hint = resolve_github_tool_account(
            session, user=user_b, account_id_hint=aid
        )
        assert resolved_hint is None

        resolved_a = resolve_github_tool_account(session, user=user_a)
        assert resolved_a is not None
        assert resolved_a.id == aid


def test_no_global_fallback_when_user_has_no_pin(client):
    user_a = _make_user("phase8-owner-a")
    user_orphan = _make_user("phase8-orphan")
    with Session(engine) as session:
        _ensure_github_tool(session)
        # Two active github accounts owned by A (and another stray with different owner)
        for name in ("gh-one", "gh-two"):
            session.add(
                ToolAccount(
                    id=str(uuid.uuid4()),
                    tool_id="github",
                    account_name=name,
                    environment="development",
                    auth_type="pat",
                    credentials_vault_ref=encrypt_secret(f"ghp_{name}"),
                    is_active=1,
                    created_by=user_a.username,
                    owner_user_id=str(user_a.id),
                    tenant_id="default",
                )
            )
        session.commit()

        # Orphan user with no pin and no owned accounts → None (no global pick)
        assert resolve_github_tool_account(session, user=user_orphan) is None

        # Owner without pin still gets only their own account
        own = resolve_github_tool_account(session, user=user_a)
        assert own is not None
        assert own.owner_user_id == str(user_a.id)


def test_get_tool_account_json_hides_secret(client, admin_token):
    h = auth_headers(admin_token)
    secret = "ghp_should_never_appear_in_get_response"
    create = client.post(
        "/api/tools/github/accounts",
        headers=h,
        json={
            "account_name": "phase8-hidden",
            "environment": "development",
            "auth_type": "pat",
            "credentials_vault_ref": secret,
        },
    )
    assert create.status_code == 200, create.text
    body = create.json()
    assert body.get("has_credentials") is True
    assert "credentials_vault_ref" not in body or body.get("credentials_vault_ref") in (
        None,
        "",
    )
    assert secret not in create.text

    aid = body["id"]
    listed = client.get("/api/tools/github/accounts", headers=h)
    assert listed.status_code == 200
    assert secret not in listed.text
    match = next(a for a in listed.json() if a["id"] == aid)
    assert match.get("has_credentials") is True
    assert match.get("credentials_vault_ref") in (None, "", False) or "credentials_vault_ref" not in match

    client.delete(f"/api/tools/github/accounts/{aid}", headers=h)
