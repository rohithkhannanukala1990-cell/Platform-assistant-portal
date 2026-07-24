"""Phase L2 — multi-LLM DB config API."""

from __future__ import annotations

from sqlmodel import Session, select

from backend.auth import LLMProviderConfig, User, engine, hash_password
from backend.tests.conftest import auth_headers


def _user_token(client, username: str, password: str = "Password123!") -> str:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if not existing:
            session.add(
                User(
                    username=username,
                    email=f"{username}@example.com",
                    hashed_password=hash_password(password),
                    role="User",
                    is_active=True,
                    tenant_id="default",
                )
            )
            session.commit()
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_admin_crud_providers_masked(client, admin_token, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    h = auth_headers(admin_token)

    created = client.post(
        "/api/llm/providers",
        headers=h,
        json={
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "api_key": "sk-test-secret-key",
            "priority": 50,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert "api_key" not in body
    assert "api_key_vault_ref" not in body
    assert body["has_api_key"] is True
    assert body["model_name"] == "gpt-4o-mini"
    pid = body["id"]

    listed = client.get("/api/llm/providers", headers=h)
    assert listed.status_code == 200
    rows = listed.json()
    assert any(r["id"] == pid for r in rows)
    for r in rows:
        assert "api_key" not in r
        assert "api_key_vault_ref" not in r

    status = client.get("/api/llm/status", headers=h)
    assert status.status_code == 200
    st = status.json()
    assert "default_model" in st
    assert "providers" in st
    assert all("api_key" not in p and "api_key_vault_ref" not in p for p in st["providers"])

    updated = client.put(
        f"/api/llm/providers/{pid}",
        headers=h,
        json={"model_name": "gpt-4o", "priority": 200},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["model_name"] == "gpt-4o"
    assert updated.json()["has_api_key"] is True  # key preserved when omitted

    deleted = client.delete(f"/api/llm/providers/{pid}", headers=h)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_non_admin_cannot_mutate(client, admin_token):
    user_tok = _user_token(client, "llm_user_l2")
    uh = auth_headers(user_tok)

    r = client.post(
        "/api/llm/providers",
        headers=uh,
        json={"provider": "openai", "model_name": "gpt-4o-mini", "api_key": "x"},
    )
    assert r.status_code == 403

    # Ensure at least one row exists via admin for PUT/DELETE targets
    ah = auth_headers(admin_token)
    created = client.post(
        "/api/llm/providers",
        headers=ah,
        json={"provider": "openai", "model_name": "gpt-4o-mini", "priority": 1},
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    assert client.put(f"/api/llm/providers/{pid}", headers=uh, json={"priority": 9}).status_code == 403
    assert client.delete(f"/api/llm/providers/{pid}", headers=uh).status_code == 403
    assert client.post("/api/llm/test", headers=uh, json={"provider_id": pid}).status_code == 403

    # Cleanup
    client.delete(f"/api/llm/providers/{pid}", headers=ah)


def test_llm_test_with_mock(client, admin_token, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    h = auth_headers(admin_token)
    created = client.post(
        "/api/llm/providers",
        headers=h,
        json={
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "priority": 999,
            "is_active": True,
        },
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    r = client.post(
        "/api/llm/test",
        headers=h,
        json={"provider_id": pid, "prompt": "hello mock"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert "AI Mock" in r.json()["response"] or "hello" in r.json()["response"].lower()

    client.delete(f"/api/llm/providers/{pid}", headers=h)


def test_get_providers_does_not_leak_vault(client, admin_token):
    h = auth_headers(admin_token)
    secret = "sk-ant-secret-should-not-leak"
    created = client.post(
        "/api/llm/providers",
        headers=h,
        json={"provider": "anthropic", "model_name": "claude-3-5-haiku-latest", "api_key": secret},
    )
    assert created.status_code == 201
    pid = created.json()["id"]

    raw = client.get("/api/llm/providers", headers=h).text
    assert secret not in raw
    assert "api_key_vault_ref" not in raw

    with Session(engine) as session:
        row = session.get(LLMProviderConfig, pid)
        assert row is not None
        assert (row.api_key_vault_ref or "").strip()

    client.delete(f"/api/llm/providers/{pid}", headers=h)
