"""Tests for /api/templates (Sprint 4 admin templates)."""


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_templates_create_list_add_tools_apply_and_use_count(client, admin_token):
    h = auth_headers(admin_token)

    r = client.post(
        "/api/templates",
        json={"name": "Pytest Blueprint", "is_published": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    created = r.json()
    tid = created["id"]
    assert created["name"] == "Pytest Blueprint"
    assert tid.startswith("tmpl-")

    r_list = client.get("/api/templates", headers=h)
    assert r_list.status_code == 200
    listed = r_list.json()
    assert any(t["id"] == tid for t in listed)

    r_tools = client.post(
        f"/api/templates/{tid}/tools",
        json={"tool_id": "github", "display_order": 0},
        headers=h,
    )
    assert r_tools.status_code == 200, r_tools.text
    tools_list = r_tools.json()
    assert isinstance(tools_list, list)
    assert len(tools_list) == 1
    assert tools_list[0]["tool_id"] == "github"

    r_tools2 = client.post(
        f"/api/templates/{tid}/tools",
        json={"tool_id": "jira", "display_order": 1},
        headers=h,
    )
    assert r_tools2.status_code == 200
    assert len(r_tools2.json()) == 2

    r_before = client.get(f"/api/templates/{tid}", headers=h)
    assert r_before.status_code == 200
    assert r_before.json()["use_count"] == 0

    r_apply = client.post(
        f"/api/templates/{tid}/apply",
        json={"workspace_name": "From Pytest Template"},
        headers=h,
    )
    assert r_apply.status_code == 200, r_apply.text
    applied = r_apply.json()
    assert applied["tools_added"] == 2
    assert applied["template_name"] == "Pytest Blueprint"
    ws = applied["workspace"]
    assert ws["name"] == "From Pytest Template"
    tool_ids = {t["tool_id"] for t in ws["tools"]}
    assert tool_ids == {"github", "jira"}

    r_after1 = client.get(f"/api/templates/{tid}", headers=h)
    assert r_after1.json()["use_count"] == 1

    r_apply2 = client.post(f"/api/templates/{tid}/apply", json={}, headers=h)
    assert r_apply2.status_code == 200
    assert r_apply2.json()["tools_added"] == 2

    r_after2 = client.get(f"/api/templates/{tid}", headers=h)
    assert r_after2.json()["use_count"] == 2
