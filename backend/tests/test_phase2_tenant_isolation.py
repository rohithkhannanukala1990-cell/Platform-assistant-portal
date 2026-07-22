"""Sprint 2 Phase 2.1 — tenant / workspace isolation."""

from __future__ import annotations

from backend.context import DEFAULT_TENANT_ID, PlatformContext, resolve_tenant_id


def test_platform_context_round_trips_tenant_id():
    ctx = PlatformContext.from_dict(
        {
            "request_id": "r1",
            "workspace_id": "ws-1",
            "tenant_id": "acme",
            "environment": "staging",
            "user_id": "alice",
            "user_role": "Admin",
        }
    )
    assert ctx.workspace_id == "ws-1"
    assert ctx.tenant_id == "acme"
    payload = ctx.to_dict()
    assert payload["tenant_id"] == "acme"
    assert payload["workspace_id"] == "ws-1"
    assert PlatformContext.from_dict(payload).tenant_id == "acme"


def test_platform_context_accepts_org_id_alias():
    ctx = PlatformContext.from_dict({"org_id": "org-9", "workspace_id": ""})
    assert ctx.tenant_id == "org-9"
    assert ctx.workspace_id is None


def test_resolve_tenant_id_defaults():
    assert resolve_tenant_id(None, "", "  ") == DEFAULT_TENANT_ID
    assert resolve_tenant_id("tenant-a", "tenant-b") == "tenant-a"


def test_workspace_list_scoped_to_tenant(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    create = client.post(
        "/api/workspaces",
        headers=headers,
        json={"name": "Tenant Scoped WS", "environment": "development"},
    )
    assert create.status_code == 200, create.text
    body = create.json()
    assert body.get("tenant_id") == DEFAULT_TENANT_ID

    listed = client.get("/api/workspaces", headers=headers)
    assert listed.status_code == 200
    ids = {w["id"] for w in listed.json()}
    assert body["id"] in ids


def test_user_create_inherits_admin_tenant(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.post(
        "/api/users/",
        headers=headers,
        json={
            "username": "tenant_user_s2",
            "password": "Passw0rd!",
            "email": "tenant_user_s2@example.com",
            "role": "User",
        },
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["tenant_id"] == DEFAULT_TENANT_ID

    users = client.get("/api/users/", headers=headers)
    assert users.status_code == 200
    names = {u["username"] for u in users.json()}
    assert "tenant_user_s2" in names
