"""Phase 4 catalog filters, dependency safety, execution, and grounding."""

from __future__ import annotations

import json
import uuid

from sqlmodel import Session

from backend.database import engine
from backend.routers.ai_assistant import _build_platform_grounding


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_entity(
    client,
    headers: dict[str, str],
    *,
    name: str,
    owner: str,
    lifecycle: str = "production",
    tags: list[str] | None = None,
) -> dict:
    response = client.post(
        "/api/catalog",
        json={
            "name": name,
            "kind": "Service",
            "lifecycle": lifecycle,
            "owner_team": owner,
            "description": f"{name} phase 4 entity",
            "tags": json.dumps(tags or []),
            "health_status": "unknown",
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_catalog_list_filters_owner_lifecycle_and_any_tag(client, admin_token):
    headers = _headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    first = _create_entity(
        client,
        headers,
        name=f"phase4-filter-a-{suffix}",
        owner=f"phase4-team-{suffix}",
        tags=["python", "observability"],
    )
    second = _create_entity(
        client,
        headers,
        name=f"phase4-filter-b-{suffix}",
        owner=f"phase4-team-{suffix}",
        tags=["go"],
    )
    _create_entity(
        client,
        headers,
        name=f"phase4-filter-c-{suffix}",
        owner="other-team",
        lifecycle="experimental",
        tags=["python"],
    )

    response = client.get(
        "/api/catalog",
        params=[
            ("owner_team", f"phase4-team-{suffix}"),
            ("lifecycle", "production"),
            ("tags", "python"),
            ("tags", "go"),
        ],
        headers=headers,
    )
    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()}
    assert first["id"] in ids
    assert second["id"] in ids


def test_catalog_delete_requires_force_when_dependencies_exist(client, admin_token):
    headers = _headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    parent = _create_entity(
        client,
        headers,
        name=f"phase4-parent-{suffix}",
        owner="platform",
    )
    child = _create_entity(
        client,
        headers,
        name=f"phase4-child-{suffix}",
        owner="platform",
    )
    dependency = client.post(
        "/api/catalog/dependencies",
        json={
            "from_entity_id": parent["id"],
            "to_entity_id": child["id"],
            "dep_type": "calls",
        },
        headers=headers,
    )
    assert dependency.status_code == 200, dependency.text

    blocked = client.delete(f"/api/catalog/{parent['id']}", headers=headers)
    assert blocked.status_code == 400
    assert "has dependencies" in blocked.json()["detail"]

    forced = client.delete(
        f"/api/catalog/{parent['id']}?force=true",
        headers=headers,
    )
    assert forced.status_code == 200, forced.text
    assert forced.json()["dependencies_deleted"] == 1


def test_golden_path_run_executes_template_steps_and_persists_outputs(
    client, admin_token
):
    headers = _headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_entity(
        client,
        headers,
        name=f"phase4-run-{suffix}",
        owner="platform",
        tags=["service"],
    )
    created = client.post(
        "/api/golden-paths",
        json={
            "name": f"Phase 4 Internal Path {suffix}",
            "slug": f"phase4-internal-{suffix}",
            "category": "Quality",
            "entity_kind": "Service",
            "steps_json": json.dumps(
                [
                    {"type": "form", "label": "Collect inputs"},
                    {
                        "type": "internal",
                        "label": "Load catalog entity",
                        "action": "catalog_lookup",
                    },
                    {
                        "type": "internal",
                        "label": "Evaluate service health",
                        "action": "evaluate_service_health",
                    },
                    {"type": "complete", "label": "Done"},
                ]
            ),
        },
        headers=headers,
    )
    assert created.status_code == 200, created.text

    response = client.post(
        f"/api/golden-paths/{created.json()['id']}/run",
        json={
            "entity_id": entity["id"],
            "inputs": {"entity_id": entity["id"], "environment": "development"},
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["outputs"]["steps_completed"] == 4
    assert len(payload["outputs"]["steps"]) == 4
    assert payload["outputs"]["steps"][1]["output"]["id"] == entity["id"]
    assert payload["outputs"]["steps"][2]["output"]["entity_id"] == entity["id"]
    assert "Step 4 completed" in payload["run_logs"]


def test_ai_grounding_lists_exact_catalog_ids_and_structured_paths(
    client, admin_token
):
    headers = _headers(admin_token)
    suffix = uuid.uuid4().hex[:8]
    entity = _create_entity(
        client,
        headers,
        name=f"phase4-grounding-{suffix}",
        owner="platform",
        tags=["python", "service"],
    )

    with Session(engine) as session:
        context = _build_platform_grounding(
            session,
            f"How can I improve {entity['id']}?",
        )

    catalog_row = next(
        row for row in context["catalog_entities"] if row["id"] == entity["id"]
    )
    assert catalog_row["name"] == entity["name"]
    assert catalog_row["tags"] == ["python", "service"]
    for path in context["golden_paths"]:
        assert path["key"]
        assert path["name"]
        assert "reason_for_recommendation" in path
        assert "estimated_duration" in path
        assert path["risk_level"] in {"low", "medium"}
