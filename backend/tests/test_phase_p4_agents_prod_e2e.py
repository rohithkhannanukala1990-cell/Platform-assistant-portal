"""Phase P4 — Agent E2E under production-like settings + HITL loop."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.database import AgentRun, Tool, ToolAccount
from backend.mcp.types import MCPTool, MCPToolResult
from backend.services.pagerduty_access import resolve_pagerduty_tool_account
from backend.services.secrets import encrypt_secret, reset_secret_box_for_tests
from backend.tests.conftest import auth_headers

pytestmark = pytest.mark.prod_e2e

FAKE_MCP_TOOLS = [
    {
        "name": "list_files",
        "description": "List files",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
    {
        "name": "delete_file",
        "description": "Delete a file permanently",
        "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
    },
]


class _FakeMCPClient:
    executed: list[tuple[str, dict]] = []

    def __init__(self, server_id: str = "", server_name: str = ""):
        self.server_id = server_id
        self.server_name = server_name

    async def list_tools(self):
        return [
            MCPTool.from_wire(t, server_id=self.server_id, server_name=self.server_name)
            for t in FAKE_MCP_TOOLS
        ]

    async def call_tool(self, name, arguments=None):
        _FakeMCPClient.executed.append((name, arguments or {}))
        return MCPToolResult(ok=True, text=f"{name} ran", content=[{"type": "text", "text": "ok"}])

    async def close(self):
        return None


@pytest.fixture
def prod_like_env(monkeypatch: pytest.MonkeyPatch):
    """Production-like process env for P4 agent E2E."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("ENABLE_DEMO_DATA", "false")
    monkeypatch.setenv("ENFORCE_WORKSPACE_ISOLATION", "true")
    monkeypatch.setenv("LLM_MOCK", "1")
    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", key)
    reset_secret_box_for_tests()
    yield key
    reset_secret_box_for_tests()


def _headers(token: str, workspace_id: str = "ws-p4") -> dict[str, str]:
    h = auth_headers(token)
    h["X-Workspace-Id"] = workspace_id
    return h


def _make_user(
    username: str,
    *,
    tenant_id: str = "default",
    role: str = "User",
    workspace_id: str = "ws-p4",
) -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.tenant_id = tenant_id
            existing.role = role
            existing.workspace_id = workspace_id
            existing.is_active = True
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password("Password123!"),
            role=role,
            is_active=True,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def _login(client, username: str) -> str:
    r = client.post(
        "/auth/login",
        data={"username": username, "password": "Password123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _ensure_tool(session: Session, tool_id: str, name: str, category: str) -> None:
    if session.get(Tool, tool_id) is None:
        session.add(Tool(id=tool_id, name=name, category=category, description=name))
        session.commit()


def _ensure_admin_workspace(admin_token: str) -> None:
    """Admin seed may lack workspace_id; pin one so ENFORCE mode allows API calls."""
    with Session(engine) as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if admin and not (admin.workspace_id or "").strip():
            admin.workspace_id = "ws-p4"
            session.add(admin)
            session.commit()


# ── 1. incident without PD → grounding none / skipped, not 500 ───────────────

def test_p4_incident_without_pd_grounding_none(client, prod_like_env):
    user = _make_user("p4-inc-a", role="Admin")
    token = _login(client, user.username)
    with patch(
        "backend.services.pagerduty_access.try_pagerduty_connector_from_context",
        return_value=None,
    ):
        r = client.post(
            "/api/agents/run",
            headers=_headers(token),
            json={
                "task": "list open incidents",
                "context": {"environment": "production"},
                "override_agents": ["incident_agent"],
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "skipped"
    assert body["grounding"] == "none"
    assert body.get("details", {}).get("reason") == "no_data" or "PagerDuty" in (body.get("summary") or "")


# ── 2. PD ToolAccount scoped to user A; user B cannot use it ─────────────────

def test_p4_pagerduty_account_scoped_to_owner(client, prod_like_env):
    user_a = _make_user("p4-pd-a", role="Admin", workspace_id="ws-p4-a")
    user_b = _make_user("p4-pd-b", role="Admin", workspace_id="ws-p4-b")
    with Session(engine) as session:
        _ensure_tool(session, "pagerduty", "PagerDuty", "comms")
        acc = ToolAccount(
            id=str(uuid.uuid4()),
            tool_id="pagerduty",
            account_name="p4-user-a-pd",
            environment="production",
            auth_type="api_key",
            credentials_vault_ref=encrypt_secret("pd_secret_user_a_only"),
            is_active=1,
            created_by=user_a.username,
            owner_user_id=str(user_a.id),
            tenant_id="default",
            workspace_id="ws-p4-a",
        )
        session.add(acc)
        session.commit()
        aid = acc.id

        assert resolve_pagerduty_tool_account(session, user=user_a) is not None
        assert resolve_pagerduty_tool_account(session, user=user_a).id == aid
        assert resolve_pagerduty_tool_account(session, user=user_b) is None
        assert resolve_pagerduty_tool_account(session, user=user_b, account_id_hint=aid) is None

    token_b = _login(client, user_b.username)
    # Isolation: resolve returns None for B even with A's account id hint;
    # agent run must not invent PD data (grounding none / skipped).
    with patch(
        "backend.services.pagerduty_access.try_pagerduty_connector_from_context",
        return_value=None,
    ):
        r = client.post(
            "/api/agents/run",
            headers=_headers(token_b, workspace_id="ws-p4-b"),
            json={
                "task": "list open incidents",
                "context": {
                    "environment": "production",
                    "tool_accounts": {"pagerduty": aid},
                },
                "override_agents": ["incident_agent"],
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grounding"] == "none"
    assert body["status"] == "skipped"
    assert "PINVENTED" not in json.dumps(body)


# ── 3. code_review with mocked GitHub → live grounding, stable JSON ──────────

def test_p4_code_review_mocked_github_live(client, prod_like_env):
    user = _make_user("p4-cr-a", role="Admin")
    token = _login(client, user.username)

    fake = MagicMock()
    fake.list_pull_requests = AsyncMock(return_value=[])
    fake.get_pull_request = AsyncMock(
        return_value={
            "number": 11,
            "title": "Harden auth",
            "html_url": "https://github.com/acme/payments/pull/11",
            "state": "open",
            "user": "dev",
        }
    )
    fake.list_pull_request_files = AsyncMock(
        return_value=[
            {
                "filename": "auth.py",
                "patch": "+token = os.environ['SECRET']\n+print(token)",
                "status": "modified",
            }
        ]
    )

    with patch(
        "backend.services.github_access.try_github_connector_from_context",
        return_value=fake,
    ), patch("backend.mcp.agent_mcp.mcp_enabled", return_value=False), patch(
        "backend.agents.code_review_agent.CodeReviewAgent._call_llm",
        new_callable=AsyncMock,
        return_value=json.dumps(
            {
                "summary": "Reviewed acme/payments PR 11",
                "findings": ["auth.py: print secret"],
                "risk_level": "high",
                "commands": [],
            }
        ),
    ):
        r = client.post(
            "/api/agents/run",
            headers=_headers(token),
            json={
                "task": "review PR #11 in acme/payments",
                "context": {"environment": "production"},
                "override_agents": ["code_review_agent"],
                "params": {"owner": "acme", "repo": "payments", "pr_number": 11},
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert "status" in body and "grounding" in body and "evidence" in body
    assert body["grounding"] in ("live", "partial")
    assert body["status"] in ("success", "skipped")
    blob = json.dumps(body, default=str)
    assert "auth.py" in blob
    assert "invented-org" not in blob.lower()


# ── 4. deploy prod → pending_approval; dry-run first; policy deny blocks ─────

def test_p4_deploy_prod_hitl_dry_run_and_deny(client, admin_token, prod_like_env):
    _ensure_admin_workspace(admin_token)
    admin_h = _headers(admin_token)

    fake_k8s = MagicMock()
    fake_k8s.list_pods = AsyncMock(
        return_value=[
            {"name": "payments-1", "namespace": "production", "status": "Running", "restarts": 0}
        ]
    )
    with patch(
        "backend.services.k8s_access.try_k8s_connector_from_context",
        return_value=fake_k8s,
    ):
        r = client.post(
            "/api/agents/run",
            headers=admin_h,
            json={
                "task": "deploy payments version 2.0.0 to production",
                "context": {"environment": "production"},
                "override_agents": ["deploy_agent"],
                "params": {
                    "service_name": "payments",
                    "version": "2.0.0",
                    "target_env": "production",
                    "dry_run": False,
                },
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requires_approval"] is True
    assert body["status"] == "pending_approval"
    run_id = body.get("run_id")
    assert run_id

    # Policy deny path: seed a pending run with an unsafe command and approve.
    deny_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            AgentRun(
                id=deny_id,
                agent="deploy_agent",
                status="pending_approval",
                summary="p4 deny approve",
                environment="production",
                tenant_id="default",
                workspace_id="ws-p4",
                requires_approval=True,
                approval_payload_json=json.dumps({"commands": ["rm -rf /"]}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    denied = client.post(f"/api/agents/{deny_id}/approve", headers=admin_h)
    assert denied.status_code == 200, denied.text
    denied_body = denied.json()
    assert denied_body["status"] == "failed"
    assert "dry-run" in (denied_body.get("execution_log") or "").lower() or "blocked" in (
        denied_body.get("execution_log") or ""
    ).lower()


# ── 5. Double approve same run_id → 400 or 409 ───────────────────────────────

def test_p4_double_approve_cas(client, admin_token, prod_like_env):
    _ensure_admin_workspace(admin_token)
    run_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            AgentRun(
                id=run_id,
                agent="auto_heal_agent",
                status="pending_approval",
                summary="p4 double approve",
                environment="production",
                tenant_id="default",
                workspace_id="ws-p4",
                requires_approval=True,
                approval_payload_json=json.dumps({"commands": []}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    h = _headers(admin_token)
    r1 = client.post(f"/api/agents/{run_id}/approve", headers=h)
    assert r1.status_code == 200, r1.text
    r2 = client.post(f"/api/agents/{run_id}/approve", headers=h)
    assert r2.status_code in {400, 409}, r2.text


# ── 6. MCP dangerous tool → pending_approval ─────────────────────────────────

def test_p4_mcp_dangerous_pending_approval(client, admin_token, prod_like_env):
    _ensure_admin_workspace(admin_token)
    _FakeMCPClient.executed = []
    h = _headers(admin_token)
    with patch(
        "backend.mcp.registry.client_for_server",
        side_effect=lambda row: _FakeMCPClient(row.id, row.name),
    ):
        created = client.post(
            "/api/mcp/servers",
            headers=h,
            json={
                "name": "p4-files-mcp",
                "transport": "stdio",
                "command": "node",
                "args": ["server.js"],
                "env": {"API_KEY": "p4-mcp-secret"},
                "require_hitl": False,
            },
        )
        assert created.status_code == 201, created.text
        server_id = created.json()["id"]
        try:
            r = client.post(
                "/api/mcp/tools/call",
                headers=h,
                json={
                    "server_id": server_id,
                    "tool": "delete_file",
                    "arguments": {"path": "/tmp/x"},
                },
            )
            assert r.status_code == 200, r.text
            call = r.json()
            assert call["status"] == "pending_approval"
            assert call.get("dangerous") is True or call.get("requires_hitl") is True
            assert _FakeMCPClient.executed == []
        finally:
            client.delete(f"/api/mcp/servers/{server_id}", headers=h)


# ── 7. kubectl delete in production → require_approval ───────────────────────

def test_p4_policy_kubectl_delete_prod_requires_approval(client, admin_token, prod_like_env):
    _ensure_admin_workspace(admin_token)
    r = client.post(
        "/api/policies/commands/evaluate",
        headers=_headers(admin_token),
        json={
            "command": "kubectl delete pod api-1 -n default",
            "environment": "production",
            "tool": "shell",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"] == "require_approval"
    assert body.get("safe_for_auto") is False


# ── 8. ENABLE_DEMO_DATA=false → no fake green / no_data ──────────────────────

def test_p4_demo_disabled_endpoints_return_no_data(client, admin_token, prod_like_env):
    _ensure_admin_workspace(admin_token)
    h = _headers(admin_token)

    dora = client.get("/api/cicd/dora-metrics", headers=h)
    assert dora.status_code == 200, dora.text
    dora_body = dora.json()
    assert dora_body.get("status") == "no_data"
    assert dora_body.get("deployment_frequency") is None

    runs = client.get("/api/cicd/active-runs", headers=h)
    assert runs.status_code == 200, runs.text
    runs_body = runs.json()
    assert runs_body.get("status") == "no_data"
    assert runs_body.get("runs") == []
    # Must not look like the old demo fixture green board.
    blob = json.dumps(runs_body).lower()
    assert "demo-payments-pipeline" not in blob
    assert "fake-green" not in blob

    anomalies = client.post("/api/logs/scan-anomalies", headers=h, json={})
    assert anomalies.status_code == 200, anomalies.text
    anom = anomalies.json()
    assert anom.get("status") == "no_data" or not anom.get("incidents")
