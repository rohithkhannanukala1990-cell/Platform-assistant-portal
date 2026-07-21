"""Tests for GET /api/standards/service/{entity_id}/health.

Empty-data behavior (documented): when both standards and scorecards are empty,
overall_status defaults to "good" (no failures or warnings detected).
"""

from unittest.mock import patch

from backend.routers.standards import (
    ScorecardResult,
    StandardResult,
    calculate_service_health_status,
)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_entity(client, headers, *, name: str) -> dict:
    response = client.post(
        "/api/catalog",
        json={
            "name": name,
            "kind": "Service",
            "lifecycle": "production",
            "owner_team": "platform",
            "language": "Python",
            "repo_url": "https://github.com/example/svc",
            "description": "Healthy enough for scorecards",
            "tags": '["api"]',
            "health_status": "healthy",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_calculate_service_health_empty_defaults_to_good():
    """Documented: empty standards + scorecards → overall_status 'good'."""
    assert calculate_service_health_status([], []) == "good"


def test_calculate_service_health_status_levels():
    fail = [StandardResult(id="s1", name="Failing", status="fail")]
    warn = [StandardResult(id="s2", name="Warning", status="warn")]
    low = [ScorecardResult(id="c1", name="Low", score=40.0, max_score=100.0)]
    mid = [ScorecardResult(id="c2", name="Mid", score=70.0, max_score=100.0)]
    high = [ScorecardResult(id="c3", name="High", score=95.0, max_score=100.0)]

    assert calculate_service_health_status(fail, high) == "poor"
    assert calculate_service_health_status([], low) == "poor"
    assert calculate_service_health_status(warn, high) == "degraded"
    assert calculate_service_health_status([], mid) == "degraded"
    assert calculate_service_health_status([], high) == "good"


def test_service_health_merges_standards_and_scorecards(client, admin_token):
    headers = auth_headers(admin_token)
    entity = _create_entity(client, headers, name="billing-service")

    response = client.get(
        f"/api/standards/service/{entity['id']}/health",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["entity_id"] == entity["id"]
    assert isinstance(body["standards"], list)
    assert isinstance(body["scorecards"], list)
    assert body["overall_status"] in {"good", "degraded", "poor"}
    # Seeded prod-readiness standard + rule-based scorecard checks should appear.
    assert len(body["standards"]) >= 1
    assert len(body["scorecards"]) >= 1
    assert all("status" in row for row in body["standards"])
    assert all("score" in row and "max_score" in row for row in body["scorecards"])


def test_service_health_empty_helpers_return_safe_default(client, admin_token):
    """When helpers yield no rows, API still returns empty lists + overall_status good."""
    headers = auth_headers(admin_token)
    entity = _create_entity(client, headers, name="empty-health-service")

    with (
        patch(
            "backend.routers.standards.evaluate_service_standards",
            return_value=[],
        ),
        patch(
            "backend.routers.standards.collect_service_scorecards",
            return_value=[],
        ),
    ):
        response = client.get(
            f"/api/standards/service/{entity['id']}/health",
            headers=headers,
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["standards"] == []
    assert body["scorecards"] == []
    assert body["overall_status"] == "good"


def test_service_health_missing_entity_returns_404(client, admin_token):
    response = client.get(
        "/api/standards/service/missing-entity/health",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404
