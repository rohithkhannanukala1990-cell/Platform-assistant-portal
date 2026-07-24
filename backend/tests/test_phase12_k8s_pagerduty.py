"""Phase 12 — K8s + PagerDuty connector parity (scoped access + ops routes)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.database import Tool, ToolAccount
from backend.services.k8s_access import resolve_k8s_tool_account
from backend.services.pagerduty_access import resolve_pagerduty_tool_account
from backend.services.secrets import encrypt_secret
from backend.tests.conftest import auth_headers


def _ensure_tool(session: Session, tool_id: str, name: str, category: str) -> None:
    if session.get(Tool, tool_id) is None:
        session.add(
            Tool(id=tool_id, name=name, category=category, description=name)
        )
        session.commit()


def _make_user(username: str) -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            return existing
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password("Password123!"),
            role="User",
            is_active=True,
            tenant_id="default",
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def test_user_b_does_not_resolve_user_a_k8s_account(client):
    user_a = _make_user("phase12-k8s-a")
    user_b = _make_user("phase12-k8s-b")
    with Session(engine) as session:
        _ensure_tool(session, "kubernetes", "Kubernetes", "kubernetes")
        acc_a = ToolAccount(
            id=str(uuid.uuid4()),
            tool_id="kubernetes",
            account_name="user-a-k8s",
            environment="development",
            auth_type="kubeconfig",
            credentials_vault_ref=encrypt_secret("apiVersion: v1\nclusters: []\n"),
            is_active=1,
            created_by=user_a.username,
            owner_user_id=str(user_a.id),
            tenant_id="default",
        )
        session.add(acc_a)
        session.commit()
        aid = acc_a.id

        assert resolve_k8s_tool_account(session, user=user_a) is not None
        assert resolve_k8s_tool_account(session, user=user_a).id == aid
        assert resolve_k8s_tool_account(session, user=user_b) is None
        assert resolve_k8s_tool_account(session, user=user_b, account_id_hint=aid) is None


def test_user_b_does_not_resolve_user_a_pagerduty_account(client):
    user_a = _make_user("phase12-pd-a")
    user_b = _make_user("phase12-pd-b")
    with Session(engine) as session:
        _ensure_tool(session, "pagerduty", "PagerDuty", "comms")
        acc_a = ToolAccount(
            id=str(uuid.uuid4()),
            tool_id="pagerduty",
            account_name="user-a-pd",
            environment="development",
            auth_type="api_key",
            credentials_vault_ref=encrypt_secret("pd_user_a_only"),
            is_active=1,
            created_by=user_a.username,
            owner_user_id=str(user_a.id),
            tenant_id="default",
        )
        session.add(acc_a)
        session.commit()
        aid = acc_a.id

        assert resolve_pagerduty_tool_account(session, user=user_a) is not None
        assert resolve_pagerduty_tool_account(session, user=user_a).id == aid
        assert resolve_pagerduty_tool_account(session, user=user_b) is None
        assert (
            resolve_pagerduty_tool_account(session, user=user_b, account_id_hint=aid)
            is None
        )


def test_k8s_pods_requires_auth(client):
    r = client.get("/api/k8s/pods")
    assert r.status_code in (401, 403)


def test_pagerduty_incidents_requires_auth(client):
    r = client.get("/api/pagerduty/incidents")
    assert r.status_code in (401, 403)


def test_k8s_pods_400_when_no_account(client, admin_token):
    h = auth_headers(admin_token)
    accounts = client.get("/api/tools/kubernetes/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/kubernetes/accounts/{acc['id']}", headers=h)

    r = client.get("/api/k8s/pods", headers=h)
    assert r.status_code == 400
    detail = r.json().get("detail") or ""
    assert "Connect a Kubernetes account in Tool Registry" in detail


def test_pagerduty_incidents_400_when_no_account(client, admin_token):
    h = auth_headers(admin_token)
    accounts = client.get("/api/tools/pagerduty/accounts", headers=h)
    assert accounts.status_code == 200
    for acc in accounts.json():
        if acc.get("is_active"):
            client.delete(f"/api/tools/pagerduty/accounts/{acc['id']}", headers=h)

    r = client.get("/api/pagerduty/incidents", headers=h)
    assert r.status_code == 400
    detail = r.json().get("detail") or ""
    assert "Connect a PagerDuty account in Tool Registry" in detail


def test_k8s_pods_list_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/kubernetes/accounts",
        headers=h,
        json={
            "account_name": "phase12-k8s",
            "environment": "development",
            "auth_type": "kubeconfig",
            "credentials_vault_ref": "apiVersion: v1\nkind: Config\nclusters: []\n",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]

    fake_pods = [
        {"name": "api-1", "status": "Running", "restarts": 0, "node": "n1", "age_seconds": 10}
    ]
    with patch("backend.routers.k8s_ops.k8s_connector_for_user") as mock_resolve:
        connector = AsyncMock()
        connector.list_pods = AsyncMock(return_value=fake_pods)
        mock_resolve.return_value = connector
        r = client.get("/api/k8s/pods?namespace=default", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()[0]["name"] == "api-1"
    client.delete(f"/api/tools/kubernetes/accounts/{aid}", headers=h)


def test_pagerduty_incidents_list_when_connected(client, admin_token):
    h = auth_headers(admin_token)
    create = client.post(
        "/api/tools/pagerduty/accounts",
        headers=h,
        json={
            "account_name": "phase12-pd",
            "environment": "development",
            "auth_type": "api_key",
            "credentials_vault_ref": "pd_test_key_phase12",
        },
    )
    assert create.status_code == 200, create.text
    aid = create.json()["id"]

    fake = [
        {
            "id": "PABC123",
            "title": "API down",
            "service": "api",
            "urgency": "high",
            "status": "triggered",
        }
    ]
    with patch(
        "backend.routers.pagerduty_ops.pagerduty_connector_for_user"
    ) as mock_resolve:
        connector = AsyncMock()
        connector.list_incidents = AsyncMock(return_value=fake)
        mock_resolve.return_value = connector
        r = client.get("/api/pagerduty/incidents", headers=h)

    assert r.status_code == 200, r.text
    assert r.json()[0]["id"] == "PABC123"
    assert "pd_test_key" not in r.text
    client.delete(f"/api/tools/pagerduty/accounts/{aid}", headers=h)
