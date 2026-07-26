"""Phase M1 — MCP client: registry masking, tool discovery, and HITL gating."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from backend.mcp.types import MCPTool, MCPToolResult, is_dangerous, is_read_only
from backend.tests.conftest import auth_headers

FAKE_TOOLS = [
    {
        "name": "list_files",
        "description": "List files in a directory",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "delete_file",
        "description": "Delete a file permanently",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
]


class FakeMCPClient:
    """Stands in for a real MCP server: records tools/list and tools/call."""

    executed: list[tuple[str, dict]] = []

    def __init__(self, server_id: str = "", server_name: str = ""):
        self.server_id = server_id
        self.server_name = server_name

    async def list_tools(self):
        return [
            MCPTool.from_wire(t, server_id=self.server_id, server_name=self.server_name)
            for t in FAKE_TOOLS
        ]

    async def call_tool(self, name, arguments=None):
        FakeMCPClient.executed.append((name, arguments or {}))
        return MCPToolResult(ok=True, text=f"{name} ran", content=[{"type": "text", "text": "ok"}])

    async def close(self):
        return None


@pytest.fixture(autouse=True)
def fake_mcp_client():
    FakeMCPClient.executed = []
    with patch(
        "backend.mcp.registry.client_for_server",
        side_effect=lambda row: FakeMCPClient(row.id, row.name),
    ):
        yield


def _create_server(client, token, **overrides) -> dict:
    body = {
        "name": overrides.pop("name", "files-mcp"),
        "transport": "stdio",
        "command": "node",
        "args": ["server.js"],
        "env": {"API_KEY": "supersecret-mcp-token"},
        "require_hitl": False,
        **overrides,
    }
    r = client.post("/api/mcp/servers", headers=auth_headers(token), json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _delete_server(client, token, server_id):
    client.delete(f"/api/mcp/servers/{server_id}", headers=auth_headers(token))


def test_tool_classification_read_vs_write():
    assert is_read_only(MCPTool(name="list_files"))
    assert is_read_only(MCPTool(name="get_issue"))
    assert not is_read_only(MCPTool(name="delete_file"))
    assert is_dangerous(MCPTool(name="deploy_service"))
    # Unknown verbs fail closed.
    assert is_dangerous(MCPTool(name="frobnicate"))
    # Server annotations win over heuristics.
    assert is_read_only(MCPTool(name="frobnicate", annotations={"readOnlyHint": True}))
    assert is_dangerous(MCPTool(name="list_files", annotations={"readOnlyHint": False}))


def test_server_crud_masks_env_secrets(client, admin_token):
    created = _create_server(client, admin_token, name="masked-mcp")
    try:
        assert created["env_keys"] == ["API_KEY"]
        assert created["has_env"] is True

        listed = client.get("/api/mcp/servers", headers=auth_headers(admin_token))
        assert listed.status_code == 200
        assert "supersecret-mcp-token" not in listed.text
        assert any(s["id"] == created["id"] for s in listed.json())

        updated = client.put(
            f"/api/mcp/servers/{created['id']}",
            headers=auth_headers(admin_token),
            json={"description": "updated", "enabled": False},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["description"] == "updated"
        assert updated.json()["enabled"] is False
        # Omitting env keeps the stored secret.
        assert updated.json()["env_keys"] == ["API_KEY"]
        assert "supersecret-mcp-token" not in updated.text
    finally:
        _delete_server(client, admin_token, created["id"])


def test_server_registry_requires_admin(client, admin_token):
    assert client.get("/api/mcp/servers").status_code in (401, 403)

    from sqlmodel import Session, select

    from backend.auth import User, hash_password, normalize_role
    from backend.database import engine

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == "mcp_viewer_m1")).first()
        if existing is None:
            session.add(
                User(
                    username="mcp_viewer_m1",
                    email="mcp_viewer_m1@example.com",
                    hashed_password=hash_password("Password123!"),
                    role=normalize_role("User"),
                    is_active=True,
                    tenant_id="default",
                )
            )
            session.commit()

    login = client.post(
        "/auth/login", data={"username": "mcp_viewer_m1", "password": "Password123!"}
    )
    assert login.status_code == 200, login.text
    user_token = login.json()["access_token"]

    r = client.get("/api/mcp/servers", headers=auth_headers(user_token))
    assert r.status_code == 403


def test_test_endpoint_lists_mocked_tools(client, admin_token):
    created = _create_server(client, admin_token, name="test-endpoint-mcp")
    try:
        r = client.post(
            f"/api/mcp/servers/{created['id']}/test", headers=auth_headers(admin_token)
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connected"] is True
        assert body["tool_count"] == 2
        assert {t["name"] for t in body["tools"]} == {"list_files", "delete_file"}
    finally:
        _delete_server(client, admin_token, created["id"])


def test_tools_catalog_flags_approval(client, admin_token):
    created = _create_server(client, admin_token, name="catalog-mcp")
    try:
        r = client.get("/api/mcp/tools", headers=auth_headers(admin_token))
        assert r.status_code == 200, r.text
        tools = {t["name"]: t for t in r.json()["tools"] if t["server_id"] == created["id"]}
        assert tools["list_files"]["read_only"] is True
        assert tools["list_files"]["require_approval"] is False
        assert tools["delete_file"]["dangerous"] is True
        assert tools["delete_file"]["require_approval"] is True
    finally:
        _delete_server(client, admin_token, created["id"])


def test_read_only_tool_auto_runs(client, admin_token):
    created = _create_server(client, admin_token, name="autorun-mcp")
    try:
        r = client.post(
            "/api/mcp/tools/call",
            headers=auth_headers(admin_token),
            json={"server_id": created["id"], "tool": "list_files", "arguments": {"path": "/tmp"}},
        )
        assert r.status_code == 200, r.text
        call = r.json()
        assert call["status"] == "completed"
        assert call["requires_hitl"] is False
        assert call["result"]["ok"] is True
        assert FakeMCPClient.executed == [("list_files", {"path": "/tmp"})]
    finally:
        _delete_server(client, admin_token, created["id"])


def test_dangerous_tool_pends_then_runs_once_on_approval(client, admin_token):
    created = _create_server(client, admin_token, name="dangerous-mcp")
    try:
        r = client.post(
            "/api/mcp/tools/call",
            headers=auth_headers(admin_token),
            json={"server_id": created["id"], "tool": "delete_file", "arguments": {"path": "/etc/x"}},
        )
        assert r.status_code == 200, r.text
        call = r.json()
        assert call["status"] == "pending_approval"
        assert call["dangerous"] is True
        # The gate must not have executed anything yet.
        assert FakeMCPClient.executed == []

        pending = client.get("/api/mcp/calls/pending", headers=auth_headers(admin_token))
        assert pending.status_code == 200
        assert any(c["id"] == call["id"] for c in pending.json())

        approved = client.post(
            f"/api/mcp/calls/{call['id']}/approve", headers=auth_headers(admin_token)
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "completed"
        assert approved.json()["approved_by"] == "admin"
        assert FakeMCPClient.executed == [("delete_file", {"path": "/etc/x"})]

        # Approving twice is refused, so the side effect stays single.
        again = client.post(
            f"/api/mcp/calls/{call['id']}/approve", headers=auth_headers(admin_token)
        )
        assert again.status_code == 400
        assert len(FakeMCPClient.executed) == 1
    finally:
        _delete_server(client, admin_token, created["id"])


def test_rejected_call_never_executes(client, admin_token):
    created = _create_server(client, admin_token, name="reject-mcp")
    try:
        call = client.post(
            "/api/mcp/tools/call",
            headers=auth_headers(admin_token),
            json={"server_id": created["id"], "tool": "delete_file", "arguments": {}},
        ).json()
        assert call["status"] == "pending_approval"

        rejected = client.post(
            f"/api/mcp/calls/{call['id']}/reject",
            headers=auth_headers(admin_token),
            json={"reason": "not authorized"},
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "rejected"
        assert FakeMCPClient.executed == []
    finally:
        _delete_server(client, admin_token, created["id"])


def test_require_hitl_server_gates_read_tools_too(client, admin_token):
    created = _create_server(client, admin_token, name="strict-mcp", require_hitl=True)
    try:
        call = client.post(
            "/api/mcp/tools/call",
            headers=auth_headers(admin_token),
            json={"server_id": created["id"], "tool": "list_files", "arguments": {}},
        ).json()
        assert call["status"] == "pending_approval"
        assert call["dangerous"] is False
        assert FakeMCPClient.executed == []
    finally:
        _delete_server(client, admin_token, created["id"])


def test_allowlist_blocks_unlisted_tool(client, admin_token):
    created = _create_server(
        client, admin_token, name="allowlist-mcp", allowlist=["list_files"]
    )
    try:
        catalog = client.get("/api/mcp/tools", headers=auth_headers(admin_token)).json()
        names = {t["name"] for t in catalog["tools"] if t["server_id"] == created["id"]}
        assert names == {"list_files"}

        blocked = client.post(
            "/api/mcp/tools/call",
            headers=auth_headers(admin_token),
            json={"server_id": created["id"], "tool": "delete_file", "arguments": {}},
        )
        assert blocked.status_code == 403
        assert FakeMCPClient.executed == []
    finally:
        _delete_server(client, admin_token, created["id"])


def test_unknown_server_is_404(client, admin_token):
    r = client.post(
        "/api/mcp/tools/call",
        headers=auth_headers(admin_token),
        json={"server_id": "does-not-exist", "tool": "list_files", "arguments": {}},
    )
    assert r.status_code == 404


def test_tool_loop_stops_at_pending_approval(client, admin_token):
    """The loop must surface the approval instead of pretending the tool ran."""
    import asyncio

    from backend.ai import tool_loop

    created = _create_server(client, admin_token, name="loop-mcp")
    try:
        tool_call_reply = (
            "```tool_call\n"
            + json.dumps({"server_id": created["id"], "tool": "delete_file", "arguments": {}})
            + "\n```"
        )

        async def fake_chat(*_args, **_kwargs):
            return tool_call_reply

        with patch("backend.ai.tool_loop.llm_service.chat", side_effect=fake_chat):
            result = asyncio.run(
                tool_loop.chat_with_tools(message="remove the file", max_rounds=3)
            )

        assert result["used_mcp"] is True
        assert result["rounds"] == 1
        assert len(result["pending_approvals"]) == 1
        assert result["pending_approvals"][0]["status"] == "pending_approval"
        assert FakeMCPClient.executed == []
    finally:
        _delete_server(client, admin_token, created["id"])


def test_tool_loop_feeds_read_results_back(client, admin_token):
    import asyncio

    from backend.ai import tool_loop

    created = _create_server(client, admin_token, name="loop-read-mcp")
    try:
        replies = [
            "```tool_call\n"
            + json.dumps({"server_id": created["id"], "tool": "list_files", "arguments": {}})
            + "\n```",
            "There are 2 files.",
        ]

        async def fake_chat(*_args, **_kwargs):
            return replies.pop(0) if replies else "done"

        with patch("backend.ai.tool_loop.llm_service.chat", side_effect=fake_chat):
            result = asyncio.run(
                tool_loop.chat_with_tools(message="what files?", max_rounds=3)
            )

        assert result["rounds"] == 2
        assert result["reply"] == "There are 2 files."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["status"] == "completed"
        assert FakeMCPClient.executed == [("list_files", {})]
    finally:
        _delete_server(client, admin_token, created["id"])
