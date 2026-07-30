"""Phase P5 — competitor gap closures (scorecards live CI, postmortem, catalog HITL)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import Session

from backend.auth import engine
from backend.routers.catalog import CatalogEntity
from backend.services.catalog_actions import execute_catalog_action, seed_catalog_actions
from backend.services.postmortem_service import (
    assert_timeline_not_invented,
    save_postmortem,
    severity_to_template_variant,
    _ensure_sections,
    _parse_action_items,
)
from backend.services.scorecard_evidence import (
    build_evidence_checks,
    build_evidence_checks_async,
    parse_github_owner_repo,
)
from backend.tests.conftest import auth_headers

pytestmark = pytest.mark.p5


def test_parse_github_owner_repo():
    assert parse_github_owner_repo("https://github.com/acme/payments") == ("acme", "payments")
    assert parse_github_owner_repo("acme/payments.git") == ("acme", "payments")


def test_scorecard_offline_metadata_source():
    entity = CatalogEntity(
        name="svc-offline",
        kind="Service",
        lifecycle="production",
        owner_team="platform",
        repo_url="https://github.com/acme/offline",
        tags='{"ci": "green", "tier": "1"}',
        health_status="healthy",
        tenant_id="default",
    )
    checks = build_evidence_checks(entity)
    ci = next(c for c in checks if c["check_name"] == "ci_green")
    assert ci["status"] == "pass"
    assert ci["evidence"]["source"] == "entity_metadata"


def test_scorecard_live_github_checks_source():
    entity = CatalogEntity(
        name="svc-live",
        kind="Service",
        lifecycle="production",
        owner_team="platform",
        repo_url="https://github.com/acme/live-ci",
        tags="{}",
        health_status="unknown",
        tenant_id="default",
    )
    fake = MagicMock()
    fake.get_repository = AsyncMock(return_value={"default_branch": "main"})
    fake.list_workflow_runs = AsyncMock(
        return_value=[
            {
                "id": 555,
                "name": "CI",
                "conclusion": "success",
                "html_url": "https://github.com/acme/live-ci/actions/runs/555",
                "head_sha": "abc1234",
            }
        ]
    )
    checks = asyncio.run(build_evidence_checks_async(entity, github_connector=fake))
    ci = next(c for c in checks if c["check_name"] == "ci_green")
    assert ci["status"] == "pass"
    assert ci["evidence"]["source"] == "github_checks"
    assert ci["evidence"]["workflow_run_id"] == 555


def test_scorecard_live_falls_back_when_no_connector():
    entity = CatalogEntity(
        name="svc-fallback",
        kind="Service",
        lifecycle="production",
        owner_team="",
        repo_url="",
        tags="{}",
        health_status="unknown",
        tenant_id="default",
    )
    checks = asyncio.run(build_evidence_checks_async(entity, github_connector=None))
    ci = next(c for c in checks if c["check_name"] == "ci_green")
    assert ci["evidence"]["source"] == "entity_metadata"
    assert ci["status"] == "fail"


def test_postmortem_sev_templates_and_no_invent():
    assert severity_to_template_variant("Critical") == "SEV1"
    assert severity_to_template_variant("High") == "SEV2"

    context = {
        "severity": "Critical",
        "summary": "API outage",
        "status": "RESOLVED",
        "root_cause": "bad deploy",
        "source": "pagerduty",
        "timestamp": "2026-01-01T00:00:00Z",
        "action_plan": ["Rollback payments", "Refresh scorecard"],
        "timeline": [
            {
                "type": "created",
                "at": "2026-01-01T00:00:00Z",
                "actor": "system",
                "detail": "Incident opened",
            }
        ],
    }
    # Fallback path (empty LLM) rebuilds from context only — no invented events.
    md, sections = _ensure_sections("", context)
    invented = assert_timeline_not_invented(md, context)
    assert invented == []
    assert "Incident opened" in (sections.get("Timeline") or "")
    assert "INVENTED-EVENT-XYZ" not in md

    items = _parse_action_items(sections, context)
    assert items
    assert any(i.get("catalog_action") == "request_scorecard_refresh" for i in items) or any(
        "scorecard" in i["title"].lower() for i in items
    )


def test_postmortem_save_action_items_and_copy_api(client, admin_token):
    from backend.database import save_incident

    inc = save_incident(
        {
            "severity": "Critical",
            "summary": "p5 postmortem",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": ["Link scorecard refresh"],
            "commands": [],
            "raw_logs": "x",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    md = "## Summary\n\nok\n\n## Impact\n\nsev1\n\n## Detection\n\ndetected\n\n## Root cause\n\nn/a\n\n## What went well\n\nok\n\n## What went wrong\n\ngap\n\n## Action items\n\n- Link scorecard refresh\n\n## Timeline\n\n- **created** — system: Incident opened\n"
    saved = save_postmortem(
        inc.id,
        tenant_id="default",
        markdown=md,
        generated_by="admin",
        template_variant="SEV1",
        context={"action_plan": ["Link scorecard refresh"], "timeline": []},
    )
    assert saved["template_variant"] == "SEV1"
    assert saved["action_items"]

    h = auth_headers(admin_token)
    r = client.get(f"/api/incidents/{inc.id}/postmortem/markdown", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Link scorecard" in (body.get("markdown") or "")
    assert isinstance(body.get("action_items"), list)


def test_catalog_propose_deploy_hitl(client, admin_token):
    from backend.auth import User
    from backend.db.models.catalog_actions import CatalogAction
    from sqlmodel import select

    with Session(engine) as session:
        seed_catalog_actions(session, tenant_id="default")
        entity = CatalogEntity(
            name="p5-deploy-svc",
            kind="Service",
            lifecycle="production",
            owner_team="platform",
            repo_url="https://github.com/acme/p5",
            tenant_id="default",
        )
        session.add(entity)
        session.commit()
        session.refresh(entity)
        eid = entity.id
        admin = session.exec(select(User).where(User.username == "admin")).first()
        assert admin is not None
        action = session.exec(
            select(CatalogAction).where(
                CatalogAction.tenant_id == "default",
                CatalogAction.action_type == "propose_deploy",
            )
        ).first()
        assert action is not None
        assert action.require_hitl is True
        session.expunge(action)
        session.expunge(entity)
        session.expunge(admin)

    result = asyncio.run(
        execute_catalog_action(
            action=action,
            entity=entity,
            user=admin,
            tenant_id="default",
            inputs={},
        )
    )
    assert result.get("ok") is True
    assert result.get("status") == "pending_approval"
    assert result.get("agent_run_id")


def test_alert_dry_run_no_mutate(client, admin_token):
    h = auth_headers(admin_token)
    # Create a suppress rule then dry-run — must not require delete cleanup for correctness.
    created = client.post(
        "/api/alert-rules",
        headers=h,
        json={
            "name": "p5-dry-suppress",
            "match_title_regex": "p5-dry-noise",
            "action": "suppress",
            "group_window_sec": 60,
            "priority": 1,
            "enabled": True,
        },
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    try:
        r = client.post(
            "/api/alert-rules/dry-run",
            headers=h,
            json={"title": "p5-dry-noise alert", "service": "payments", "severity": "low"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["matched"] is True
        assert body["action"] == "suppress"
        assert body["would_mutate"] is False

        stats = client.get("/api/alert-rules/stats", headers=h)
        assert stats.status_code == 200
        assert "suppressed_total" in stats.json()
    finally:
        client.delete(f"/api/alert-rules/{rule_id}", headers=h)
