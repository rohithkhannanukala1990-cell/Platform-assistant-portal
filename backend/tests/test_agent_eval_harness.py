"""Phase P3 — shared agent eval harness driven by fixtures/agents/*.json."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

from backend.agents import get_agent
from backend.context import PlatformContext
from backend.database import engine
from backend.routers.catalog import CatalogEntity

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "agents"


def _load_fixtures() -> list[Path]:
    paths = sorted(FIXTURES_DIR.glob("*.json"))
    assert paths, f"No fixtures found in {FIXTURES_DIR}"
    return paths


def _ctx(data: dict) -> PlatformContext:
    defaults = {
        "user_id": "eval-user",
        "user_role": "Admin",
        "environment": "development",
        "tenant_id": "default",
        "workspace_id": "ws-eval",
        "workspace_name": "eval",
    }
    defaults.update(data or {})
    return PlatformContext(**defaults)


def _blob(result) -> str:
    parts = [
        result.summary or "",
        json.dumps(result.details or {}, default=str),
        json.dumps(result.evidence or [], default=str),
        json.dumps(result.recommended_actions or [], default=str),
        json.dumps(result.approval_payload or {}, default=str),
        " ".join(result.errors or []),
    ]
    return " ".join(parts).lower()


def _build_connector(spec: Any) -> MagicMock | None:
    if spec is None:
        return None
    conn = MagicMock()
    for method, value in (spec or {}).items():
        if isinstance(value, list) or isinstance(value, dict) or value is None:
            setattr(conn, method, AsyncMock(return_value=value))
        else:
            setattr(conn, method, AsyncMock(return_value=value))
    # Sensible defaults so unexpected calls don't invent data.
    for name in (
        "list_incidents",
        "list_pull_requests",
        "list_pull_request_files",
        "list_repos",
        "list_pods",
        "list_workflow_run_jobs",
    ):
        if not hasattr(conn, name) or not isinstance(getattr(conn, name), AsyncMock):
            setattr(conn, name, AsyncMock(return_value=[]))
    if not hasattr(conn, "get_pull_request") or not isinstance(conn.get_pull_request, AsyncMock):
        conn.get_pull_request = AsyncMock(return_value={})
    if not hasattr(conn, "get_workflow_run") or not isinstance(conn.get_workflow_run, AsyncMock):
        conn.get_workflow_run = AsyncMock(return_value={})
    return conn


def _policy_effect(result) -> str | None:
    if result.policy and isinstance(result.policy, dict):
        return result.policy.get("effect")
    details = result.details or {}
    if details.get("policy_effect"):
        return details.get("policy_effect")
    if result.requires_approval:
        return "require_approval"
    return None


def _assert_expected(result, expected: dict) -> None:
    if "grounding" in expected:
        assert result.grounding in expected["grounding"], (
            f"grounding={result.grounding} not in {expected['grounding']}"
        )
    if "status_in" in expected:
        assert result.status in expected["status_in"], (
            f"status={result.status} not in {expected['status_in']}"
        )
    if "requires_approval" in expected:
        assert bool(result.requires_approval) is bool(expected["requires_approval"])

    blob = _blob(result)
    for needle in expected.get("must_contain") or []:
        assert needle.lower() in blob, f"missing must_contain: {needle}"
    for needle in expected.get("must_not_contain") or []:
        assert needle.lower() not in blob, f"found must_not_contain: {needle}"

    if expected.get("commands_empty"):
        cmds = (result.details or {}).get("commands") or []
        payload_cmds = (result.approval_payload or {}).get("commands") or []
        # Deny / read-only: details.commands empty; approval payload may be empty too.
        if result.status == "failed" and (result.policy or {}).get("effect") == "deny":
            assert cmds == []
        elif result.requires_approval:
            # HITL may keep commands in approval_payload — still not auto-executable success path
            assert result.status in ("pending_approval", "dry_run", "success")
        else:
            assert list(cmds) == []
            assert list(payload_cmds) == []

    policy_exp = expected.get("commands_policy")
    if policy_exp is not None:
        effect = _policy_effect(result)
        if isinstance(policy_exp, list):
            assert effect in policy_exp, f"policy effect={effect} not in {policy_exp}"
        else:
            assert effect == policy_exp, f"policy effect={effect} != {policy_exp}"

    for needle in expected.get("recommended_actions_must_match") or []:
        ra_blob = json.dumps(result.recommended_actions or [], default=str).lower()
        assert needle.lower() in ra_blob, f"recommended_actions missing: {needle}"

    min_checks = expected.get("min_checks")
    if min_checks is not None:
        checks = (result.details or {}).get("checks") or (result.details or {}).get("scorecards") or []
        assert len(checks) >= int(min_checks), f"expected >= {min_checks} checks, got {len(checks)}"


@pytest.mark.parametrize("fixture_path", _load_fixtures(), ids=lambda p: p.stem)
def test_agent_eval_fixture(
    fixture_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client,  # noqa: ARG001 — ensures app lifespan creates tables + policy seeds
) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    agent = get_agent(fixture["agent"])
    context = _ctx(fixture.get("context") or {})
    params = dict(fixture.get("params") or {})
    mocks = fixture.get("mock_tools") or {}
    expected = fixture.get("expected") or {}
    mode = fixture.get("mode") or "run"

    if mocks.get("llm_mock"):
        monkeypatch.setenv("LLM_MOCK", "1")

    entity_cleanup_id: str | None = None
    setup = fixture.get("setup") or {}
    if setup.get("catalog_entity"):
        with Session(engine) as session:
            row = CatalogEntity(**setup["catalog_entity"])
            session.add(row)
            session.commit()
            session.refresh(row)
            entity_cleanup_id = row.id
            if setup.get("pass_entity_id"):
                params["entity_id"] = row.id

    patchers: list[Any] = []
    try:
        if "pagerduty" in mocks:
            pd = _build_connector(mocks["pagerduty"])
            patchers.append(patch.object(agent, "_ground_pd", AsyncMock(return_value=pd)))
        if "github" in mocks:
            gh = _build_connector(mocks["github"])
            patchers.append(patch.object(agent, "_ground_github", AsyncMock(return_value=gh)))
        if "k8s" in mocks:
            k8s = _build_connector(mocks["k8s"])
            patchers.append(patch.object(agent, "_ground_k8s", AsyncMock(return_value=k8s)))
        if "mcp_enabled" in mocks:
            patchers.append(
                patch("backend.mcp.agent_mcp.mcp_enabled", return_value=bool(mocks["mcp_enabled"]))
            )
            if not mocks["mcp_enabled"]:
                patchers.append(
                    patch(
                        "backend.mcp.agent_mcp.list_github_repos_prefer_mcp",
                        AsyncMock(return_value=([], "none")),
                    )
                )
        if "alert_rules" in mocks:
            patchers.append(
                patch(
                    "backend.agents.alert_noise_agent.list_alert_rules",
                    return_value=mocks["alert_rules"],
                )
            )
        if "llm_json" in mocks:
            payload = mocks["llm_json"]
            raw = payload if isinstance(payload, str) else json.dumps(payload)
            patchers.append(patch.object(agent, "_call_llm", AsyncMock(return_value=raw)))

        for p in patchers:
            p.start()

        if mode == "finalize":
            result = agent.finalize_result(
                context,
                summary=fixture.get("summary") or "eval finalize",
                details=dict(fixture.get("details") or {}),
                commands=list(fixture.get("commands") or []),
                evidence=list(fixture.get("evidence") or []),
                grounding=fixture.get("grounding") or "partial",
                task=str(params.get("task") or "eval"),
            )
        else:
            with Session(engine) as session:
                result = asyncio.run(agent.run(params, context, session))

        _assert_expected(result, expected)
    finally:
        for p in reversed(patchers):
            p.stop()
        if entity_cleanup_id:
            with Session(engine) as session:
                row = session.get(CatalogEntity, entity_cleanup_id)
                if row:
                    session.delete(row)
                    session.commit()


def test_eval_fixtures_cover_required_scenarios() -> None:
    names = {p.stem for p in _load_fixtures()}
    required = {
        "incident_list_no_pd",
        "incident_list_live_pd",
        "code_review_with_files",
        "code_review_disconnected",
        "pipeline_failed_run",
        "auto_heal_prod_needs_approval",
        "auto_heal_deny_rm_rf",
        "deploy_prod_hitl",
        "scorecard_evidence_only",
        "alert_noise_rules",
        "infra_kubectl_get_allow_dev",
        "migration_prod_backup_reminder",
    }
    missing = required - names
    assert not missing, f"Missing required fixtures: {sorted(missing)}"
