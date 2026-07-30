"""Tests for GET /api/golden-paths/applicable.

Invalid template_id / entity_id behavior: the API returns HTTP 404
(not an empty list) when the referenced record is missing or inactive.
"""

from sqlmodel import Session, select

from backend.database import engine
from backend.routers.golden_paths import GoldenPathTemplate


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_template(client, headers, *, name: str, category: str) -> dict:
    response = client.post(
        "/api/templates",
        json={
            "name": name,
            "category": category,
            "is_published": True,
            "recommended_golden_path_keys": [],
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_entity(client, headers, *, name: str, kind: str = "Service") -> dict:
    response = client.post(
        "/api/catalog",
        json={
            "name": name,
            "kind": kind,
            "lifecycle": "production",
            "owner_team": "platform",
            "description": f"{name} for applicable-path tests",
            "tags": '["service"]',
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_applicable_for_template_returns_affinity_matched_paths(client, admin_token):
    headers = auth_headers(admin_token)
    template = _create_template(
        client,
        headers,
        name="Onboarding Blueprint",
        category="onboarding",
    )

    with Session(engine) as session:
        onboarding_keys = {
            row.slug
            for row in session.exec(
                select(GoldenPathTemplate).where(
                    GoldenPathTemplate.is_active == True,  # noqa: E712
                    GoldenPathTemplate.category == "Onboarding",
                )
            ).all()
        }
        platform_keys = {
            row.slug
            for row in session.exec(
                select(GoldenPathTemplate).where(
                    GoldenPathTemplate.is_active == True,  # noqa: E712
                    GoldenPathTemplate.category == "Platform",
                )
            ).all()
        }

    response = client.get(
        f"/api/golden-paths/applicable?template_id={template['id']}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    keys = {item["key"] for item in response.json()["items"]}

    # onboarding affinity → Onboarding + Platform categories
    assert onboarding_keys.issubset(keys)
    assert platform_keys.issubset(keys)
    assert "create-new-service" in keys


def test_applicable_invalid_template_id_returns_404(client, admin_token):
    """Documented behavior: missing template_id → 404 (not empty items)."""
    response = client.get(
        "/api/golden-paths/applicable?template_id=tmpl-does-not-exist",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_applicable_invalid_entity_id_returns_404(client, admin_token):
    """Documented behavior: missing entity_id → 404 (not empty items)."""
    response = client.get(
        "/api/golden-paths/applicable?entity_id=missing-entity",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_applicable_for_entity_returns_kind_matched_paths(client, admin_token):
    headers = auth_headers(admin_token)
    entity = _create_entity(client, headers, name="payments-api", kind="Service")

    with Session(engine) as session:
        expected = {
            row.slug
            for row in session.exec(
                select(GoldenPathTemplate).where(
                    GoldenPathTemplate.is_active == True,  # noqa: E712
                    GoldenPathTemplate.entity_kind == "Service",
                )
            ).all()
        }
        # Production lifecycle also surfaces Quality / Operations paths.
        expected |= {
            row.slug
            for row in session.exec(
                select(GoldenPathTemplate).where(
                    GoldenPathTemplate.is_active == True  # noqa: E712
                )
            ).all()
            if (row.category or "") in {"Quality", "Operations"}
        }

    response = client.get(
        f"/api/golden-paths/applicable?entity_id={entity['id']}",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    keys = {item["key"] for item in response.json()["items"]}
    assert expected.issubset(keys)
    assert "create-new-service" in keys
    assert "add-observability" in keys


def test_applicable_requires_template_or_entity(client, admin_token):
    response = client.get(
        "/api/golden-paths/applicable",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 400
