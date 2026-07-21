"""Capability enforcement for platform-content and entity-operation routes."""

from datetime import datetime, timezone

from sqlmodel import Session

from backend.auth import User, get_current_user
from backend.database import UserRole, engine
from backend.main import app


def _as_role(role: str, username: str | None = None):
    def dependency() -> User:
        return User(
            id=999,
            username=username or f"{role.lower()}-test",
            email="",
            hashed_password="unused",
            role=role,
        )

    return dependency


def test_unknown_role_cannot_view_templates(client):
    app.dependency_overrides[get_current_user] = _as_role("Unknown")
    try:
        response = client.get("/api/templates")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_viewer_can_view_content_but_cannot_trigger_entity_action(client):
    app.dependency_overrides[get_current_user] = _as_role("Viewer")
    try:
        templates = client.get("/api/templates")
        paths = client.get("/api/golden-paths")
        action = client.post(
            "/api/catalog/missing/actions/missing/run",
            json={"inputs_json": {}},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert templates.status_code == 200
    assert paths.status_code == 200
    assert action.status_code == 403
    assert action.json()["detail"] == "Forbidden"


def test_database_role_assignment_overrides_legacy_user_fallback(client):
    assignment_id = "ur-capability-viewer-test"
    username = "assigned-viewer-test"
    with Session(engine) as session:
        session.add(
            UserRole(
                id=assignment_id,
                user_id=username,
                role_id="role-viewer",
                scope_type="global",
                scope_id="",
                granted_by="pytest",
                granted_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    app.dependency_overrides[get_current_user] = _as_role("User", username)
    try:
        templates = client.get("/api/templates")
        action = client.post(
            "/api/catalog/missing/actions/missing/run",
            json={"inputs_json": {}},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        with Session(engine) as session:
            assignment = session.get(UserRole, assignment_id)
            if assignment:
                session.delete(assignment)
                session.commit()

    assert templates.status_code == 200
    assert action.status_code == 403
    assert action.json()["detail"] == "Forbidden"


def test_developer_can_reach_health_and_entity_action_handlers(client):
    app.dependency_overrides[get_current_user] = _as_role("Developer")
    try:
        health = client.get("/api/standards/service/missing/health")
        action = client.post(
            "/api/catalog/missing/actions/missing/run",
            json={"inputs_json": {}},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # A 404 proves authorization passed and the route reached entity lookup.
    assert health.status_code == 404
    assert action.status_code == 404


def test_missing_view_capabilities_return_403_on_new_endpoints(client):
    """Users without VIEW_* grants get 403 on templates / golden paths / health."""
    app.dependency_overrides[get_current_user] = _as_role("Unknown")
    try:
        templates = client.get("/api/templates")
        categories = client.get("/api/templates/categories")
        golden_paths = client.get("/api/golden-paths")
        applicable = client.get(
            "/api/golden-paths/applicable?template_id=tmpl-x"
        )
        health = client.get("/api/standards/service/entity-x/health")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    for response in (templates, categories, golden_paths, applicable, health):
        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"
