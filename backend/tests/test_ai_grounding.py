"""AI assistant grounding: golden-path + health helpers for known entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.routers.ai_assistant import _build_platform_grounding
from backend.routers.standards import ScorecardResult, StandardResult


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
            "description": f"{name} entity",
            "tags": '["service"]',
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_platform_grounding_calls_health_and_paths_for_known_entity(client, admin_token):
    entity = _create_entity(
        client, auth_headers(admin_token), name="checkout-service"
    )
    fake_path = SimpleNamespace(
        id=1,
        slug="create-new-service",
        name="Create New Service",
        description="Scaffold",
        category="Onboarding",
        entity_kind="Service",
        steps_json="[]",
    )

    with (
        patch(
            "backend.routers.standards.evaluate_service_standards",
            return_value=[
                StandardResult(id="std-1", name="Prod Ready", status="warn")
            ],
        ) as evaluate_mock,
        patch(
            "backend.routers.standards.collect_service_scorecards",
            return_value=[
                ScorecardResult(
                    id="sc-1", name="Docs", score=80.0, max_score=100.0, grade="warn"
                )
            ],
        ) as scorecards_mock,
        patch(
            "backend.routers.golden_paths.find_applicable_paths_for_entity",
            return_value=[fake_path],
        ) as paths_mock,
    ):
        from sqlmodel import Session

        from backend.database import engine

        with Session(engine) as session:
            context = _build_platform_grounding(
                session,
                f"How do I improve {entity['name']}?",
            )

    evaluate_mock.assert_called_once()
    scorecards_mock.assert_called_once()
    paths_mock.assert_called_once()
    assert context["entity"]["id"] == entity["id"]
    assert context["service_health"]["overall_status"] in {
        "good",
        "degraded",
        "poor",
    }
    assert context["golden_paths"][0]["key"] == "create-new-service"
    assert context["intent"]["health"] is True


def test_platform_grounding_skips_helpers_for_unrelated_prompt(client, admin_token):
    # Ensure at least one entity exists so a skipped call is meaningful.
    _create_entity(client, auth_headers(admin_token), name="ignored-service")

    with (
        patch(
            "backend.routers.standards.evaluate_service_standards"
        ) as evaluate_mock,
        patch(
            "backend.routers.standards.collect_service_scorecards"
        ) as scorecards_mock,
        patch(
            "backend.routers.golden_paths.find_applicable_paths_for_entity"
        ) as paths_mock,
    ):
        from sqlmodel import Session

        from backend.database import engine

        with Session(engine) as session:
            context = _build_platform_grounding(
                session,
                "What is the weather in Paris today?",
            )

    evaluate_mock.assert_not_called()
    scorecards_mock.assert_not_called()
    paths_mock.assert_not_called()
    assert context["entity"] is None
    assert context["service_health"] is None
    assert context["golden_paths"] == []
    assert context["templates"] == []


def test_ai_chat_grounds_known_entity_via_helpers(client, admin_token):
    headers = auth_headers(admin_token)
    entity = _create_entity(client, headers, name="orders-api")

    with (
        patch(
            "backend.routers.ai_assistant.llm_router.chat",
            new_callable=AsyncMock,
            return_value="Use the create-new-service path and fix readiness gaps.",
        ),
        patch(
            "backend.routers.standards.evaluate_service_standards",
            return_value=[],
        ) as evaluate_mock,
        patch(
            "backend.routers.standards.collect_service_scorecards",
            return_value=[],
        ) as scorecards_mock,
        patch(
            "backend.routers.golden_paths.find_applicable_paths_for_entity",
            return_value=[],
        ) as paths_mock,
    ):
        response = client.post(
            "/api/ai/chat",
            json={"message": f"How can I improve {entity['name']} compliance?"},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    evaluate_mock.assert_called_once()
    scorecards_mock.assert_called_once()
    paths_mock.assert_called_once()


def test_ai_chat_skips_helpers_when_prompt_unrelated(client, admin_token):
    headers = auth_headers(admin_token)
    _create_entity(client, headers, name="silent-service")

    with (
        patch(
            "backend.routers.ai_assistant.llm_router.chat",
            new_callable=AsyncMock,
            return_value="I can help with platform operations.",
        ),
        patch(
            "backend.routers.standards.evaluate_service_standards"
        ) as evaluate_mock,
        patch(
            "backend.routers.standards.collect_service_scorecards"
        ) as scorecards_mock,
        patch(
            "backend.routers.golden_paths.find_applicable_paths_for_entity"
        ) as paths_mock,
    ):
        response = client.post(
            "/api/ai/chat",
            json={"message": "Tell me a joke about cats"},
            headers=headers,
        )

    assert response.status_code == 200, response.text
    evaluate_mock.assert_not_called()
    scorecards_mock.assert_not_called()
    paths_mock.assert_not_called()
