"""RBAC API tests (Sprint 5 part 1)."""


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_rbac_create_role_assign_permissions_check(client, admin_token):
    h = auth_headers(admin_token)

    r = client.post(
        "/api/rbac/roles",
        json={
            "name": "Pytest Custom Role",
            "description": "test",
            "permissions": ["workspaces:read", "tools:read"],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    role = r.json()
    rid = role["id"]
    assert role["slug"].startswith("pytest-custom-role")
    assert len(role["permissions"]) == 2

    r2 = client.get("/api/rbac/roles", headers=h)
    assert r2.status_code == 200
    assert any(x["id"] == rid for x in r2.json())

    r_assign = client.post(
        "/api/rbac/users/admin/roles",
        json={"user_id": "admin", "role_id": rid, "scope_type": "global"},
        headers=h,
    )
    assert r_assign.status_code == 200, r_assign.text
    data = r_assign.json()
    assert "workspaces:read" in data["effective_permissions"]
    assert "tools:read" in data["effective_permissions"]

    r_perm = client.get("/api/rbac/users/admin/permissions", headers=h)
    assert r_perm.status_code == 200
    pj = r_perm.json()
    assert "workspaces:read" in pj["permissions"]
    assert "tools:read" in pj["permissions"]

    ok = client.post(
        "/api/rbac/check",
        json={
            "user_id": "admin",
            "resource": "workspaces",
            "action": "read",
            "scope_type": "global",
            "scope_id": "",
        },
        headers=h,
    )
    assert ok.status_code == 200
    assert ok.json()["allowed"] is True

    deny = client.post(
        "/api/rbac/check",
        json={
            "user_id": "admin",
            "resource": "workspaces",
            "action": "delete",
            "scope_type": "global",
            "scope_id": "",
        },
        headers=h,
    )
    assert deny.status_code == 200
    assert deny.json()["allowed"] is False
