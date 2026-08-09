"""Sprint 3: connector write-back methods, policy registration, artifact HITL."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session, select

from backend.auth import AuditLog, User, engine, hash_password
from backend.connectors.confluence_connector import ConfluenceConnector
from backend.connectors.jira_connector import JiraConnector
from backend.connectors.servicenow_connector import ServiceNowConnector
from backend.context import PlatformContext
from backend.db.models.policy import CommandPolicyRule
from backend.mcp.portal_tools import WRITE_TOOLS
from backend.services.artifact_service import (
    ArtifactApproval,
    fulfill_artifact_approval,
    propose_artifact,
    reject_artifact_approval,
)
from backend.tests.conftest import auth_headers


REQUIRED_APPROVAL_NAMES = [
    "approval-jira-create-issue",
    "approval-jira-transition-issue",
    "approval-jira-comment-on-issue",
    "approval-jira-link-issues",
    "approval-slack-post-thread-reply",
    "approval-slack-post-approval-request",
    "approval-slack-update-message",
    "approval-servicenow-create-change-request",
    "approval-servicenow-update-change-state",
    "approval-servicenow-create-incident",
    "approval-confluence-create-page",
    "approval-confluence-update-page",
    "approval-github-add-pr-review",
]

REQUIRED_WRITE_TOOLS = {
    "portal_jira_create_issue",
    "portal_jira_transition_issue",
    "portal_jira_comment_on_issue",
    "portal_jira_link_issues",
    "portal_slack_post_thread_reply",
    "portal_slack_post_approval_request",
    "portal_slack_update_message",
    "portal_servicenow_create_change_request",
    "portal_servicenow_update_change_state",
    "portal_servicenow_create_incident",
    "portal_confluence_create_page",
    "portal_confluence_update_page",
    "portal_github_add_pr_review",
}


@pytest.fixture
def admin_headers(client, admin_token):
    return auth_headers(admin_token)


def test_write_methods_registered_as_require_approval(client):
    # Ensure seed ran via lifespan
    from backend.db.core import _seed_github_editor_policy

    _seed_github_editor_policy()
    with Session(engine) as session:
        names = {
            r.name
            for r in session.exec(select(CommandPolicyRule)).all()
            if r.effect == "require_approval"
        }
    for name in REQUIRED_APPROVAL_NAMES:
        assert name in names, f"missing policy rule {name}"


def test_write_tools_in_write_tools_set():
    missing = REQUIRED_WRITE_TOOLS - WRITE_TOOLS
    assert not missing, f"missing WRITE_TOOLS entries: {missing}"


@pytest.mark.asyncio
async def test_dependency_drift_proposes_without_creating_pr(client, admin_headers):
    from backend.agents.dependency_drift_agent import dependency_drift_agent

    ctx = PlatformContext(
        user_id="admin",
        user_role="Admin",
        tenant_id="default",
        environment="development",
    )
    fake = MagicMock()
    fake.get_file_contents = AsyncMock(
        return_value='{"dependencies":{"left-pad":"^0.0.1"}}'
    )
    with patch.object(dependency_drift_agent, "_ground_github", AsyncMock(return_value=fake)):
        with Session(engine) as db:
            result = await dependency_drift_agent.run(
                {
                    "repo": "acme/app",
                    "propose": True,
                    "proposed_content": '{"dependencies":{"left-pad":"^1.0.0"}}',
                },
                ctx,
                db,
            )
    assert result.status == "pending_approval"
    assert result.details.get("source") == "artifact"
    assert result.details.get("artifact_approval_id")
    # Nothing created yet — no github write calls
    assert not hasattr(fake, "create_pull_request") or not fake.create_pull_request.called


@pytest.mark.asyncio
async def test_approve_creates_one_pr_idempotent(client, admin_headers):
    from backend.auth import User
    from sqlmodel import select as sel

    with Session(engine) as session:
        admin = session.exec(sel(User).where(User.username == "admin")).first()

    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="dependency_drift_agent",
        connector="github",
        method="github_dependency_pr",
        params={
            "repo": "acme/app",
            "path": "package.json",
            "content": '{"dependencies":{"x":"1.0.0"}}',
            "branch_name": "deps/test",
            "base": "main",
            "title": "bump",
            "body": "body",
        },
        preview={"type": "github_pr", "diff_preview": '{"dependencies":{"x":"1.0.0"}}'},
        grounding="live",
        summary="test propose",
    )
    approval_id = proposal["id"]
    calls = {"n": 0}

    async def fake_exec(**kwargs):
        calls["n"] += 1
        params = kwargs.get("params") or {}
        assert params.get("content") == '{"dependencies":{"x":"1.0.0"}}'
        return {"ok": True, "url": "https://github.com/acme/app/pull/9", "number": 9}

    with patch(
        "backend.services.artifact_service._execute_connector_write",
        new=AsyncMock(side_effect=fake_exec),
    ):
        out1 = await fulfill_artifact_approval(
            approval_id=approval_id,
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
        out2 = await fulfill_artifact_approval(
            approval_id=approval_id,
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
    assert out1.get("ok") is True
    assert out1.get("url") == "https://github.com/acme/app/pull/9"
    assert out2.get("idempotent") is True
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_reject_writes_audit(client, admin_headers):
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="security_agent",
        connector="jira",
        method="create_issue",
        params={"project_key": "SEC", "summary": "x", "description": "y"},
        preview={"type": "jira_issue", "summary": "x"},
        grounding="live",
        summary="reject me",
    )
    reject_artifact_approval(
        approval_id=proposal["id"],
        tenant_id="default",
        decided_by="admin",
        reason="not needed",
    )
    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).where(AuditLog.event_type == "artifact_rejected")
        ).all()
        assert any("admin" in (r.detail or "") for r in rows)
        row = session.get(ArtifactApproval, proposal["id"])
        assert row.status == "rejected"


@pytest.mark.asyncio
async def test_security_maps_critical_to_highest():
    from backend.agents.security_agent import security_agent

    ctx = PlatformContext(
        user_id="admin",
        user_role="Admin",
        tenant_id="default",
        environment="development",
    )
    fake_jira = MagicMock()
    with patch.object(security_agent, "_ground_aws", AsyncMock(return_value=MagicMock())):
        with patch.object(security_agent, "_ground_jira", AsyncMock(return_value=fake_jira)):
            with Session(engine) as db:
                result = await security_agent.run(
                    {
                        "findings": [
                            {
                                "severity": "CRITICAL",
                                "title": "Open SG",
                                "arn": "arn:aws:guardduty:finding/1",
                                "description": "fix it",
                            }
                        ],
                        "propose": True,
                        "project_key": "SEC",
                    },
                    ctx,
                    db,
                )
    assert result.status == "pending_approval"
    assert result.details.get("proposed_priority") == "Highest"
    assert result.approval_payload.get("preview", {}).get("priority") == "Highest"


@pytest.mark.asyncio
async def test_jira_invalid_transition_lists_options():
    conn = JiraConnector(
        {
            "instance_url": "https://example.atlassian.net",
            "account_identifier": "u@example.com",
            "api_token": "tok",
        }
    )

    async def fake_request(method, path, **kwargs):
        if method == "GET" and "transitions" in path:
            return {
                "ok": True,
                "transitions": [
                    {"id": "11", "name": "Start Progress"},
                    {"id": "21", "name": "Done"},
                ],
            }
        return {"ok": True}

    with patch.object(conn, "_request", side_effect=fake_request):
        out = await conn.transition_issue("SEC-1", "Not A Real Transition")
    assert out.get("ok") is False
    assert "Start Progress" in (out.get("error") or "")
    assert "Done" in (out.get("available_transitions") or [])


@pytest.mark.asyncio
async def test_servicenow_unknown_state_lists_options():
    conn = ServiceNowConnector(
        {"instance_url": "https://example.service-now.com", "api_key": "tok"}
    )
    out = await conn.update_change_state("abc", "not-a-state")
    assert out.get("ok") is False
    assert "assess" in (out.get("valid_states") or [])


@pytest.mark.asyncio
async def test_confluence_stale_version_conflict():
    conn = ConfluenceConnector(
        {
            "instance_url": "https://example.atlassian.net/wiki",
            "account_identifier": "u@example.com",
            "api_token": "tok",
        }
    )

    async def fake_request(method, path, **kwargs):
        return {
            "ok": False,
            "status_code": 409,
            "error": "conflict",
            "message": "Page changed upstream — version is stale.",
        }

    with patch.object(conn, "_request", side_effect=fake_request):
        out = await conn.update_page("123", "Title", "<p>x</p>", version=3)
    assert out.get("status_code") == 409
    assert "stale" in (out.get("message") or "").lower() or out.get("error") == "conflict"


@pytest.mark.asyncio
async def test_agents_no_data_when_connector_missing():
    from backend.agents.cost_agent import cost_agent
    from backend.agents.security_agent import security_agent

    ctx = PlatformContext(
        user_id="admin",
        user_role="Admin",
        tenant_id="default",
        environment="development",
    )
    with patch.object(security_agent, "_ground_aws", AsyncMock(return_value=MagicMock())):
        with patch.object(security_agent, "_ground_jira", AsyncMock(return_value=None)):
            with Session(engine) as db:
                r = await security_agent.run(
                    {
                        "findings": [{"severity": "HIGH", "title": "x"}],
                        "propose": True,
                    },
                    ctx,
                    db,
                )
    assert r.status == "skipped"
    assert "Jira" in (r.details.get("missing_tools") or [])

    fake_aws = MagicMock()
    fake_aws.get_cost_explorer = AsyncMock(
        return_value=[{"service": "EC2", "amount": "10", "unit": "USD"}]
    )
    with patch.object(cost_agent, "_ground_aws", AsyncMock(return_value=fake_aws)):
        with patch.object(cost_agent, "_ground_jira", AsyncMock(return_value=None)):
            with Session(engine) as db:
                r2 = await cost_agent.run({"propose": True}, ctx, db)
    assert r2.status == "skipped"
    assert "Jira" in (r2.details.get("missing_tools") or [])


@pytest.mark.asyncio
async def test_execute_uses_db_content_not_request():
    from backend.auth import User
    from sqlmodel import select as sel

    with Session(engine) as session:
        admin = session.exec(sel(User).where(User.username == "admin")).first()

    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="tester_agent",
        connector="github",
        method="github_dependency_pr",
        params={
            "repo": "acme/app",
            "path": "tests/t.py",
            "content": "FROZEN_FROM_DB",
            "branch_name": "test/x",
            "base": "main",
            "title": "t",
            "body": "b",
        },
        preview={"diff_preview": "FROZEN_FROM_DB"},
        grounding="live",
        summary="freeze test",
    )

    seen = {}

    async def fake_exec(**kwargs):
        seen["params"] = kwargs.get("params")
        return {"ok": True, "url": "https://example.com/pr/1"}

    with patch(
        "backend.services.artifact_service._execute_connector_write",
        new=AsyncMock(side_effect=fake_exec),
    ):
        await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
    assert seen["params"]["content"] == "FROZEN_FROM_DB"
