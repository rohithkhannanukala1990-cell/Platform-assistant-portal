"""Phase M2 — Portal MCP server: list tools, token auth, read tools with mocks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.mcp.portal_tools import PORTAL_TOOLS, WRITE_TOOLS
from backend.mcp.server_app import PortalMCPServer, require_auth
from backend.mcp.types import MCPError


@pytest.fixture
def mcp_token(monkeypatch):
    monkeypatch.setenv("PORTAL_MCP_TOKEN", "test-portal-mcp-token")
    monkeypatch.setenv("MCP_ENABLED", "true")
    return "test-portal-mcp-token"


def test_list_tools_includes_read_and_write(mcp_token):
    server = PortalMCPServer()
    tools = server.list_tools()
    names = {t["name"] for t in tools}
    assert "portal_list_incidents" in names
    assert "portal_get_incident" in names
    assert "portal_list_catalog_services" in names
    assert "portal_search" in names
    assert "portal_health_summary" in names
    assert "portal_list_github_repos" in names
    assert "portal_propose_remediation" in names
    assert "portal_run_agent" in names

    # WRITE_TOOLS is the portal-wide registry of connector write methods that
    # must be HITL-gated — it pairs with the `approval-<connector>-<method>`
    # CommandPolicyRule rows asserted by the sprint 3/4/5 tests. Most of its
    # entries (Jira/Slack/ServiceNow/Confluence/AWS/Okta/... write-backs) are
    # reached through agents and connectors, and are deliberately not exposed
    # as MCP tools, so `WRITE_TOOLS.issubset(names)` is not a real invariant —
    # an unexposed name is inert (dispatch_tool returns "Unknown tool").
    #
    # The invariant that does matter is the reverse: every write tool the MCP
    # server *does* expose must be classified in WRITE_TOOLS, or server_app
    # would silently skip its pending-approval annotation on tools/call.
    mcp_write_tools = {
        t["name"] for t in tools if not (t.get("annotations") or {}).get("readOnlyHint")
    }
    assert mcp_write_tools, "MCP server exposes no write tools"
    unclassified = mcp_write_tools - WRITE_TOOLS
    assert not unclassified, f"MCP write tools missing from WRITE_TOOLS: {unclassified}"
    assert len(tools) == len(PORTAL_TOOLS)


def test_reject_tools_list_without_token(monkeypatch):
    monkeypatch.setenv("PORTAL_MCP_TOKEN", "secret-token")
    monkeypatch.setenv("MCP_ENABLED", "true")
    server = PortalMCPServer()

    async def _run():
        return await server.handle(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )

    # No token in params and env extract uses expected_token — when params empty,
    # extract_token falls back to env, so clear env to simulate missing client token.
    monkeypatch.delenv("PORTAL_MCP_TOKEN", raising=False)
    monkeypatch.setenv("PORTAL_MCP_TOKEN", "")  # server misconfigured
    resp = asyncio.run(_run())
    assert "error" in resp
    assert "PORTAL_MCP_TOKEN" in resp["error"]["message"]


def test_reject_invalid_token(mcp_token):
    server = PortalMCPServer()

    async def _run():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {"token": "wrong-token"},
            }
        )

    resp = asyncio.run(_run())
    assert "error" in resp
    assert "Unauthorized" in resp["error"]["message"]


def test_require_auth_helper(mcp_token):
    require_auth({"token": mcp_token})
    with pytest.raises(MCPError, match="Unauthorized"):
        require_auth({"token": "nope"})


def test_tools_list_with_valid_token(mcp_token):
    server = PortalMCPServer()

    async def _run():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/list",
                "params": {"token": mcp_token},
            }
        )

    resp = asyncio.run(_run())
    assert "result" in resp
    assert len(resp["result"]["tools"]) >= 8


def test_initialize_requires_token(mcp_token):
    server = PortalMCPServer()

    async def _run_bad():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "initialize",
                "params": {"token": "bad"},
            }
        )

    async def _run_ok():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test"},
                    "token": mcp_token,
                },
            }
        )

    bad = asyncio.run(_run_bad())
    assert "error" in bad
    ok = asyncio.run(_run_ok())
    assert ok["result"]["serverInfo"]["name"] == "platform-assistant-portal"


def test_read_tool_list_incidents_mocked(mcp_token):
    server = PortalMCPServer()
    fake = [
        {"id": 1, "summary": "disk full", "status": "OPEN", "tenant_id": "default"},
        {"id": 2, "summary": "oom", "status": "OPEN", "tenant_id": "default"},
    ]

    async def _run():
        with patch(
            "backend.mcp.portal_tools.list_incidents", return_value=fake
        ) as mocked:
            resp = await server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "token": mcp_token,
                        "name": "portal_list_incidents",
                        "arguments": {"limit": 10},
                    },
                }
            )
            mocked.assert_called()
            return resp

    resp = asyncio.run(_run())
    assert "result" in resp
    assert resp["result"]["isError"] is False
    text = resp["result"]["content"][0]["text"]
    assert "disk full" in text
    assert "oom" in text


def test_read_tool_health_summary_mocked(mcp_token):
    server = PortalMCPServer()

    async def _run():
        with patch(
            "backend.mcp.portal_tools.health_checker.get_summary",
            new=AsyncMock(
                return_value={
                    "status": "ok",
                    "recommendation_count": 0,
                    "slow_query_count": 0,
                }
            ),
        ):
            return await server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "token": mcp_token,
                        "name": "portal_health_summary",
                        "arguments": {},
                    },
                }
            )

    resp = asyncio.run(_run())
    assert resp["result"]["isError"] is False
    assert "ok" in resp["result"]["content"][0]["text"]


def test_read_tool_github_repos_mocked(mcp_token):
    server = PortalMCPServer()
    fake_repos = [{"full_name": "acme/alpha", "html_url": "https://github.com/acme/alpha"}]

    class _Conn:
        async def list_repos(self, per_page=20):
            return fake_repos

    async def _run():
        with patch(
            "backend.mcp.portal_tools.try_github_connector_from_context",
            return_value=_Conn(),
        ):
            return await server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": 12,
                    "method": "tools/call",
                    "params": {
                        "token": mcp_token,
                        "name": "portal_list_github_repos",
                        "arguments": {"per_page": 5},
                    },
                }
            )

    resp = asyncio.run(_run())
    assert resp["result"]["isError"] is False
    assert "acme/alpha" in resp["result"]["content"][0]["text"]


def test_propose_remediation_is_hitl_pending(client, admin_token, mcp_token):
    """Write tool stages AWAITING_APPROVAL — does not execute commands."""
    from backend.tests.conftest import auth_headers
    from sqlmodel import Session

    from backend.database import engine
    from backend.db.models.ops import Incident

    with Session(engine) as session:
        row = Incident(
            severity="High",
            summary="mcp propose target",
            root_cause="test",
            raw_logs="",
            model_used="test",
            raw_response="{}",
            status="OPEN",
            tenant_id="default",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        incident_id = row.id

    server = PortalMCPServer()

    async def _run():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "token": mcp_token,
                    "name": "portal_propose_remediation",
                    "arguments": {
                        "incident_id": incident_id,
                        "plan": ["scale up replicas", "clear disk"],
                    },
                },
            }
        )

    resp = asyncio.run(_run())
    assert resp["result"]["isError"] is False
    body = resp["result"]["structuredContent"]
    assert body["status"] == "pending_approval"
    assert body["hitl"] is True

    detail = client.get(
        f"/api/incidents/{incident_id}", headers=auth_headers(admin_token)
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "AWAITING_APPROVAL"


def test_run_agent_queues_pending_approval(mcp_token):
    server = PortalMCPServer()

    async def _run():
        return await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {
                    "token": mcp_token,
                    "name": "portal_run_agent",
                    "arguments": {
                        "agent": "code_review_agent",
                        "task": "review open PRs",
                    },
                },
            }
        )

    resp = asyncio.run(_run())
    assert resp["result"]["isError"] is False
    body = resp["result"]["structuredContent"]
    assert body["status"] == "pending_approval"
    assert body["run_id"]
    assert body["hitl"] is True
