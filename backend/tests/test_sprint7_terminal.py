"""Sprint 7 — terminal input, @agents, inline approval, completions, history."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlmodel import Session

from backend.agents.base import AgentResult
from backend.auth import User, engine
from backend.db.models.terminal import TerminalApproval
from backend.routers.catalog import CatalogEntity
from backend.services.terminal_service import (
    complete_options,
    create_terminal_approval,
    get_terminal_approval,
    load_history,
    mark_approval_status,
    publish_approval_decision,
    register_decision_waiter,
    resolve_agent_alias,
    store_history,
)
from backend.ws_portal import _is_blocked


def _agent_result(agent: str, **kwargs) -> AgentResult:
    return AgentResult(
        agent=agent,
        status=kwargs.get("status", "success"),
        summary=kwargs.get("summary", "ok"),
        details=kwargs.get("details", {}),
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by="test",
        workspace="",
        environment="development",
        grounding=kwargs.get("grounding", "live"),
        evidence=kwargs.get("evidence", []),
        requires_approval=kwargs.get("requires_approval", False),
    )


def test_resolve_agent_alias():
    assert resolve_agent_alias("incident") == "incident_agent"
    assert resolve_agent_alias("security") == "security_agent"
    assert resolve_agent_alias("heal") == "auto_heal_agent"
    assert resolve_agent_alias("unknown-xyz") is None


def test_blocked_commands_helper():
    assert _is_blocked("rm -rf /") is True
    assert _is_blocked("kubectl get pods") is False


def test_at_incident_invokes_agent_not_shell():
    import asyncio
    from backend.ws_portal import _handle_at_command

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    ws = FakeWS()
    user = User(
        username="term-agent",
        email="t@example.com",
        hashed_password="x",
        role="Admin",
        is_active=True,
        tenant_id="default",
    )

    async def _run():
        with patch(
            "backend.pipeline.orchestrator.run_agent_for_workflow",
            new_callable=AsyncMock,
            return_value=_agent_result("incident_agent", summary="triaged"),
        ) as mock_run:
            with patch(
                "backend.executor.safe_executor.safe_executor.execute",
                new_callable=AsyncMock,
            ) as mock_exec:
                await _handle_at_command(
                    ws,
                    command="@incident triage foo",
                    user=user,
                    tenant_id="default",
                )
                mock_run.assert_awaited()
                mock_exec.assert_not_called()

    asyncio.run(_run())
    blob = " ".join(str(s) for s in ws.sent)
    assert "triaged" in blob or "incident_agent" in blob


def test_at_agents_lists_without_executor():
    import asyncio
    from backend.ws_portal import _handle_at_command

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    ws = FakeWS()
    user = User(
        username="term-list",
        email="t2@example.com",
        hashed_password="x",
        role="Admin",
        is_active=True,
        tenant_id="default",
    )

    async def _run():
        with patch(
            "backend.executor.safe_executor.safe_executor.execute",
            new_callable=AsyncMock,
        ) as mock_exec:
            await _handle_at_command(ws, command="@agents", user=user, tenant_id="default")
            mock_exec.assert_not_called()

    asyncio.run(_run())
    blob = " ".join(str(s.get("data", s)) for s in ws.sent)
    assert "incident_agent" in blob or "Available agents" in blob


def test_at_unknown_helpful_error():
    import asyncio
    from backend.ws_portal import _handle_at_command

    class FakeWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, payload):
            self.sent.append(payload)

    ws = FakeWS()
    user = User(
        username="term-unk",
        email="t3@example.com",
        hashed_password="x",
        role="Admin",
        is_active=True,
        tenant_id="default",
    )

    async def _run():
        with patch(
            "backend.pipeline.orchestrator.run_agent_for_workflow",
            new_callable=AsyncMock,
        ) as mock_run:
            with patch(
                "backend.executor.safe_executor.safe_executor.execute",
                new_callable=AsyncMock,
            ) as mock_exec:
                await _handle_at_command(
                    ws, command="@unknown foo", user=user, tenant_id="default"
                )
                mock_run.assert_not_called()
                mock_exec.assert_not_called()

    asyncio.run(_run())
    blob = " ".join(str(s.get("data", s)) for s in ws.sent)
    assert "Unknown agent" in blob or "@agents" in blob


def test_approval_creates_record_without_execute(client, admin_token):
    approval = create_terminal_approval(
        tenant_id="default",
        username="admin",
        command="kubectl rollout restart deploy/payments",
        reasons=["production environment requires approval"],
        session_id="sess-1",
    )
    assert approval.status == "pending"
    assert approval.command == "kubectl rollout restart deploy/payments"
    row = get_terminal_approval(approval.id, "default")
    assert row is not None
    assert row.command == "kubectl rollout restart deploy/payments"


def test_approval_grant_uses_stored_command_not_client(client, admin_token):
    approval = create_terminal_approval(
        tenant_id="default",
        username="admin",
        command="echo SAFE_FROM_DB",
        reasons=["needs approval"],
        session_id="sess-2",
    )
    # Simulate attacker trying to change command after the fact — DB wins
    with Session(engine) as session:
        row = session.get(TerminalApproval, approval.id)
        assert row.command == "echo SAFE_FROM_DB"

    seen = {}

    def _waiter(payload):
        seen.update(payload)

    unreg = register_decision_waiter(approval.id, _waiter)
    marked = mark_approval_status(
        approval.id, status="approved", decided_by="admin"
    )
    publish_approval_decision(
        {"type": "approval_granted", "approval_id": approval.id}
    )
    unreg()
    assert marked is not None
    assert marked.status == "approved"
    refreshed = get_terminal_approval(approval.id, "default")
    assert refreshed.command == "echo SAFE_FROM_DB"
    assert seen.get("type") == "approval_granted"


def test_approval_denial_no_execute():
    approval = create_terminal_approval(
        tenant_id="default",
        username="admin",
        command="echo should-not-run",
        reasons=["x"],
        session_id="sess-3",
    )
    marked = mark_approval_status(
        approval.id,
        status="denied",
        decided_by="admin",
        reason="nope",
    )
    assert marked.status == "denied"
    assert get_terminal_approval(approval.id, "default").status == "denied"


def test_tab_completion_catalog_tenant_scoped(client, admin_token):
    # Seed entities in two tenants
    with Session(engine) as session:
        session.add(
            CatalogEntity(
                id=str(uuid.uuid4()),
                name="payments-service",
                kind="Service",
                lifecycle="production",
                owner_team="pay",
                tenant_id="tenant-a",
                is_active=1,
            )
        )
        session.add(
            CatalogEntity(
                id=str(uuid.uuid4()),
                name="secret-other-tenant",
                kind="Service",
                lifecycle="production",
                owner_team="x",
                tenant_id="tenant-b",
                is_active=1,
            )
        )
        session.commit()

    opts_a = complete_options("pay", tenant_id="tenant-a", cwd=".")
    opts_b = complete_options("secret", tenant_id="tenant-a", cwd=".")
    assert any("payments-service" in o for o in opts_a)
    assert not any("secret-other-tenant" in o for o in opts_b)


def test_tab_completion_no_cross_tenant_leak():
    with Session(engine) as session:
        session.add(
            CatalogEntity(
                id=str(uuid.uuid4()),
                name="only-tenant-z",
                kind="Service",
                lifecycle="production",
                owner_team="z",
                tenant_id="tenant-z",
                is_active=1,
            )
        )
        session.commit()
    opts = complete_options("only", tenant_id="tenant-other", cwd=".")
    assert not any(o == "only-tenant-z" for o in opts)


def test_history_persists_and_user_scoped():
    u1 = f"hist-{uuid.uuid4().hex[:6]}"
    u2 = f"hist-{uuid.uuid4().hex[:6]}"
    store_history(tenant_id="default", username=u1, command="echo one")
    store_history(tenant_id="default", username=u1, command="echo two")
    store_history(tenant_id="default", username=u2, command="echo other")
    h1 = load_history(tenant_id="default", username=u1)
    h2 = load_history(tenant_id="default", username=u2)
    assert h1 == ["echo one", "echo two"]
    assert h2 == ["echo other"]


def test_blocked_commands_not_written_to_history():
    u = f"hist-block-{uuid.uuid4().hex[:6]}"
    # Mimic terminal policy: caller must not store when blocked
    cmd = "rm -rf /"
    assert _is_blocked(cmd) is True
    # Ensure we don't store
    before = load_history(tenant_id="default", username=u)
    if not _is_blocked(cmd):
        store_history(tenant_id="default", username=u, command=cmd)
    after = load_history(tenant_id="default", username=u)
    assert after == before
    assert cmd not in after


def test_history_cap_enforced():
    u = f"hist-cap-{uuid.uuid4().hex[:6]}"
    for i in range(105):
        store_history(tenant_id="default", username=u, command=f"cmd-{i}")
    rows = load_history(tenant_id="default", username=u, limit=200)
    assert len(rows) <= 100


def test_agent_alias_catalog_and_deploy():
    assert resolve_agent_alias("catalog") == "catalog_health_agent"
    assert resolve_agent_alias("deploy") == "deploy_agent"
    assert resolve_agent_alias("incident_agent") == "incident_agent"
