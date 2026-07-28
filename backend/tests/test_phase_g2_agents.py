"""Phase G2 — Agent platform grounding, guardrails, evidence."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import Session

from backend.agents import AGENT_REGISTRY, get_agent, list_agents
from backend.agents.base import BaseAgent, GROUNDING_RULES
from backend.agents.code_review_agent import CodeReviewAgent
from backend.agents.incident_agent import IncidentAgent
from backend.agents.auto_heal_agent import AutoHealAgent
from backend.agents.scorecard_agent import ScorecardAgent
from backend.context import PlatformContext
from backend.database import engine
from backend.pipeline.orchestrator import _ensure_context, orchestrator_agent
from backend.services.command_policy import PolicyDecision


def _ctx(**kwargs) -> PlatformContext:
    defaults = dict(
        user_id="g2-user",
        user_role="Admin",
        environment="development",
        tenant_id="default",
        workspace_id="ws-g2",
        workspace_name="g2",
    )
    defaults.update(kwargs)
    return PlatformContext(**defaults)


# ── 1. incident_agent without PD → grounding none / no_data ──────────────────

def test_incident_agent_no_pagerduty_returns_no_data():
    agent = IncidentAgent()
    with Session(engine) as session:
        with patch.object(agent, "_ground_pd", AsyncMock(return_value=None)):
            result = asyncio.run(
                agent.run({"task": "list open incidents"}, _ctx(), session)
            )
    assert result.status == "skipped"
    assert result.grounding == "none"
    assert "PagerDuty" in result.summary or result.details.get("reason") == "no_data"


# ── 2. code_review does not invent a second repo ─────────────────────────────

def test_code_review_uses_only_provided_github_evidence():
    agent = CodeReviewAgent()
    fake_connector = MagicMock()
    fake_connector.list_pull_requests = AsyncMock(
        return_value=[
            {
                "number": 42,
                "title": "Fix disk",
                "html_url": "https://github.com/acme/only-repo/pull/42",
                "user": {"login": "dev"},
                "head": {"ref": "fix"},
                "base": {"ref": "main"},
            }
        ]
    )
    fake_connector.list_pull_request_files = AsyncMock(
        return_value=[{"filename": "app.py", "patch": "+print(1)", "status": "modified"}]
    )
    fake_connector.get_pull_request = AsyncMock(
        return_value={
            "number": 42,
            "title": "Fix disk",
            "html_url": "https://github.com/acme/only-repo/pull/42",
            "state": "open",
            "user": "dev",
        }
    )

    with Session(engine) as session:
        with patch.object(agent, "_ground_github", AsyncMock(return_value=fake_connector)):
            with patch("backend.mcp.agent_mcp.mcp_enabled", return_value=False):
                with patch.object(
                    agent,
                    "_call_llm",
                    AsyncMock(
                        return_value='{"summary":"Reviewed acme/only-repo PR 42","findings":["app.py:1 low print"],"risk_level":"low","details":{}}'
                    ),
                ):
                    result = asyncio.run(
                        agent.run(
                            {
                                "task": "review PR #42 in acme/only-repo",
                                "owner": "acme",
                                "repo": "only-repo",
                                "pr_number": 42,
                            },
                            _ctx(),
                            session,
                        )
                    )

    assert result.grounding in ("live", "partial")
    blob = str(result.details) + str(result.evidence) + result.summary
    assert "acme/only-repo" in blob or "only-repo" in blob
    assert "second-repo" not in blob.lower()
    assert "invented-org" not in blob.lower()


# ── 3. auto_heal with deny policy does not succeed execute ───────────────────

def test_auto_heal_deny_policy_does_not_mark_success_execute():
    agent = AutoHealAgent()
    deny = PolicyDecision(
        effect="deny",
        reasons=["baseline_blocklist: Recursive force file deletion"],
        matched_rule_ids=["baseline_blocklist"],
    )
    fake_k8s = MagicMock()
    fake_k8s.list_pods = AsyncMock(
        return_value=[
            {
                "name": "api-1",
                "namespace": "default",
                "status": "CrashLoopBackOff",
                "restarts": 12,
            }
        ]
    )

    with Session(engine) as session:
        with patch.object(agent, "_ground_k8s", AsyncMock(return_value=fake_k8s)):
            with patch.object(agent, "_apply_command_policy", return_value=deny):
                with patch.object(agent, "_execute", AsyncMock()) as exec_mock:
                    result = asyncio.run(
                        agent.run({"task": "heal crashing pods"}, _ctx(), session)
                    )
                    exec_mock.assert_not_called()

    assert result.status == "failed"
    assert result.policy and result.policy.get("effect") == "deny"
    assert result.requires_approval is False


# ── 4. scorecard with LLM_MOCK / non-LLM path returns checks ─────────────────

def test_scorecard_agent_returns_checks_without_fantasy(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    agent = ScorecardAgent()
    fake_db = MagicMock()
    fake_db.exec = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]), first=MagicMock(return_value=None)))
    result = asyncio.run(agent.run({"task": "score services"}, _ctx(), fake_db))
    assert result.status in ("success", "skipped")
    assert result.grounding in ("live", "partial", "none")
    if result.status == "skipped":
        assert result.grounding == "none"
    else:
        assert isinstance(result.details, dict)
        assert result.grounding == "live"  # empty checks still live from DB


# ── 5. orchestrator rejects missing user_id ──────────────────────────────────

def test_orchestrator_requires_user_id():
    ctx = PlatformContext(
        user_id="",
        user_role="Admin",
        environment="development",
        tenant_id="default",
    )
    try:
        _ensure_context(ctx)
        raised = False
    except ValueError:
        raised = True
    assert raised

    with Session(engine) as session:
        result = asyncio.run(
            orchestrator_agent.run("do something", ctx, session, override_agents=["cost_agent"])
        )
    assert result.status == "failed"
    assert "user_id" in result.summary.lower() or any("user_id" in e for e in result.errors)


# ── 6. all agents import and register ────────────────────────────────────────

def test_all_agents_registered_and_importable():
    listed = list_agents()
    names = {a["name"] for a in listed}
    assert len(AGENT_REGISTRY) == 17
    assert len(names) == 17
    for name in AGENT_REGISTRY:
        agent = get_agent(name)
        assert isinstance(agent, BaseAgent)
        assert agent.name == name
    assert "migration_agent" in AGENT_REGISTRY
    assert "You must only use facts" in GROUNDING_RULES


def test_base_no_data_helper():
    class _T(BaseAgent):
        name = "tmp"
        primary_tools = ["GitHub"]

    r = _T()._no_data_result(_ctx(), "missing github", missing_tools=["GitHub"])
    assert r.status == "skipped"
    assert r.grounding == "none"
    assert r.confidence == 0.0
    assert r.evidence
