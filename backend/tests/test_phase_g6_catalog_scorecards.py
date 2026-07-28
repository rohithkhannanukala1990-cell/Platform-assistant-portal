"""Phase G6 — catalog self-service actions + evidence-based scorecards."""

from __future__ import annotations

import json
import uuid

from sqlmodel import Session

from backend.database import engine
from backend.db.models.ai_models import AgentRun
from backend.db.models.catalog_actions import (
    ACTION_OPEN_INCIDENT,
    ACTION_PROPOSE_DEPLOY,
    ACTION_REQUEST_SCORECARD_REFRESH,
    ACTION_RUN_GOLDEN_PATH,
)
from backend.routers.catalog import CatalogEntity
from backend.services.scorecard_evidence import (
    CHECK_WEIGHTS,
    build_evidence_checks,
    weighted_overall_score,
)
from backend.tests.conftest import auth_headers


def _create_service(client, headers: dict, *, name: str, tags: str | None = None, **extra) -> dict:
    body = {
        "name": name,
        "kind": "Service",
        "lifecycle": "production",
        "owner_team": extra.pop("owner_team", "platform"),
        "description": f"{name} g6 entity",
        "tags": tags or "[]",
        "health_status": extra.pop("health_status", "healthy"),
        "repo_url": extra.pop("repo_url", "https://github.com/example/svc"),
        **extra,
    }
    r = client.post("/api/catalog", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_builtin_catalog_actions_seeded(client, admin_token):
    h = auth_headers(admin_token)
    r = client.get("/api/catalog-actions", headers=h)
    assert r.status_code == 200, r.text
    types = {a["action_type"] for a in r.json()}
    assert ACTION_RUN_GOLDEN_PATH in types
    assert ACTION_REQUEST_SCORECARD_REFRESH in types
    assert ACTION_OPEN_INCIDENT in types
    assert ACTION_PROPOSE_DEPLOY in types
    propose = next(a for a in r.json() if a["action_type"] == ACTION_PROPOSE_DEPLOY)
    assert propose["require_hitl"] is True
    assert propose["risk"] == "high"


def test_evidence_checks_offline_pass_fail():
    entity = CatalogEntity(
        id=str(uuid.uuid4()),
        name="g6-evidence",
        kind="Service",
        lifecycle="production",
        owner_team="sre",
        repo_url="https://github.com/acme/api",
        tags=json.dumps(
            {
                "runbook_url": "https://runbooks.example/api",
                "oncall_link": "https://pd.example/sched/1",
                "tier": "1",
                "ci": "green",
            }
        ),
        health_status="healthy",
        is_active=1,
    )
    checks = build_evidence_checks(entity)
    names = {c["check_name"] for c in checks}
    assert names == set(CHECK_WEIGHTS.keys())
    assert all(c["status"] == "pass" for c in checks)
    assert weighted_overall_score(checks) == 100
    assert all(isinstance(c.get("evidence"), dict) for c in checks)

    bare = CatalogEntity(
        id=str(uuid.uuid4()),
        name="g6-bare",
        kind="Service",
        lifecycle="experimental",
        owner_team="",
        repo_url=None,
        tags="[]",
        health_status="unknown",
        is_active=1,
    )
    fail_checks = build_evidence_checks(bare)
    assert all(c["status"] == "fail" for c in fail_checks)
    assert weighted_overall_score(fail_checks) == 0


def test_scorecard_evaluate_persists_evidence(client, admin_token):
    h = auth_headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_service(
        client,
        h,
        name=f"g6-score-{suffix}",
        tags=json.dumps(
            {
                "runbook": "https://rb.example/x",
                "oncall": "https://oncall.example/x",
                "tier": "2",
                "ci": "green",
            }
        ),
    )
    r = client.post(f"/api/catalog/{entity['id']}/scorecard/evaluate", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("version") == "v2"
    assert data["overall_score"] == 100
    assert len(data["checks"]) == 6
    for check in data["checks"]:
        assert check["status"] == "pass"
        assert isinstance(check.get("evidence"), dict)
        assert check.get("weight", 0) > 0

    got = client.get(f"/api/catalog/{entity['id']}/scorecard", headers=h)
    assert got.status_code == 200
    assert got.json()["overall_score"] == 100
    assert got.json()["checks"][0]["evidence"]


def test_request_scorecard_refresh_action(client, admin_token):
    h = auth_headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_service(client, h, name=f"g6-refresh-{suffix}")
    actions = client.get(f"/api/catalog/{entity['id']}/catalog-actions", headers=h)
    assert actions.status_code == 200
    refresh = next(a for a in actions.json() if a["action_type"] == ACTION_REQUEST_SCORECARD_REFRESH)
    r = client.post(
        f"/api/catalog-actions/{refresh['id']}/execute",
        headers=h,
        json={"entity_id": entity["id"]},
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["status"] == "completed"
    assert result["ok"] is True


def test_open_incident_action(client, admin_token):
    h = auth_headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_service(client, h, name=f"g6-inc-{suffix}")
    actions = client.get("/api/catalog-actions", headers=h).json()
    open_inc = next(a for a in actions if a["action_type"] == ACTION_OPEN_INCIDENT)
    r = client.post(
        f"/api/catalog-actions/{open_inc['id']}/execute",
        headers=h,
        json={"entity_id": entity["id"], "inputs": {"severity": "Critical"}},
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["status"] == "completed"
    assert result.get("incident_id")


def test_propose_deploy_requires_hitl(client, admin_token):
    h = auth_headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_service(client, h, name=f"g6-deploy-{suffix}")
    actions = client.get(f"/api/catalog/{entity['id']}/catalog-actions", headers=h).json()
    propose = next(a for a in actions if a["action_type"] == ACTION_PROPOSE_DEPLOY)
    assert propose["require_hitl"] is True

    r = client.post(
        f"/api/catalog-actions/{propose['id']}/execute",
        headers=h,
        json={"entity_id": entity["id"], "inputs": {"environment": "production"}},
    )
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["status"] == "pending_approval"
    assert result["require_hitl"] is True
    run_id = result["agent_run_id"]
    assert run_id

    with Session(engine) as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.status == "pending_approval"
        assert run.requires_approval is True
        detail = json.loads(run.details_json or "{}")
        assert detail.get("action_type") == ACTION_PROPOSE_DEPLOY
        assert detail.get("entity_id") == entity["id"]


def test_propose_deploy_not_on_non_service(client, admin_token):
    h = auth_headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/api/catalog",
        headers=h,
        json={
            "name": f"g6-lib-{suffix}",
            "kind": "Library",
            "lifecycle": "production",
            "owner_team": "libs",
            "description": "lib",
            "tags": "[]",
            "health_status": "unknown",
        },
    )
    assert r.status_code == 200, r.text
    entity = r.json()
    actions = client.get(f"/api/catalog/{entity['id']}/catalog-actions", headers=h).json()
    types = {a["action_type"] for a in actions}
    assert ACTION_PROPOSE_DEPLOY not in types


def test_catalog_actions_require_auth(client):
    assert client.get("/api/catalog-actions").status_code == 401
