"""Sprint 8 — connected code editor: persistence, PR HITL, agents, GitHub."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlmodel import Session, select

from backend.agents.base import AgentResult
from backend.auth import User, engine, hash_password
from backend.db.models.editor import EditorFile, EditorPRApproval
from backend.services.editor_service import detect_language, make_idempotency_key
from backend.tests.conftest import auth_headers
from datetime import datetime, timezone


def _make_user(username: str, *, tenant_id: str, role: str = "Admin") -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.tenant_id = tenant_id
            existing.role = role
            existing.is_active = True
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing
        u = User(
            username=username,
            email=f"{username}@example.com",
            hashed_password=hash_password("Password123!"),
            role=role,
            is_active=True,
            tenant_id=tenant_id,
        )
        session.add(u)
        session.commit()
        session.refresh(u)
        return u


def _login(client, username: str, password: str = "Password123!") -> str:
    r = client.post("/auth/login", data={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_file_round_trip(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={"filename": "app.yaml", "content": "apiVersion: v1\n"},
    )
    assert created.status_code == 201, created.text
    fid = created.json()["id"]
    got = client.get(f"/api/editor/files/{fid}", headers=h)
    assert got.status_code == 200
    assert got.json()["content"] == "apiVersion: v1\n"
    saved = client.put(
        f"/api/editor/files/{fid}",
        headers=h,
        json={"content": "apiVersion: apps/v1\n"},
    )
    assert saved.status_code == 200
    assert saved.json()["content"] == "apiVersion: apps/v1\n"
    again = client.get(f"/api/editor/files/{fid}", headers=h)
    assert again.json()["content"] == "apiVersion: apps/v1\n"


def test_cross_tenant_file_404(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={"filename": "secret.yaml", "content": "x: 1\n"},
    ).json()
    other = _make_user(f"ed-x-{uuid.uuid4().hex[:6]}", tenant_id="tenant-other")
    token = _login(client, other.username)
    r = client.get(f"/api/editor/files/{created['id']}", headers=auth_headers(token))
    assert r.status_code == 404


def test_same_tenant_other_user_cannot_read(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={"filename": "mine.yaml", "content": "owner: admin\n"},
    ).json()
    # Peer in default tenant
    peer = _make_user(f"ed-peer-{uuid.uuid4().hex[:6]}", tenant_id="default", role="User")
    token = _login(client, peer.username)
    r = client.get(f"/api/editor/files/{created['id']}", headers=auth_headers(token))
    assert r.status_code == 404


def test_github_not_connected_clear_error(client, admin_token):
    h = auth_headers(admin_token)
    with patch(
        "backend.services.editor_service.try_github_connector_from_context",
        return_value=None,
    ):
        r = client.get(
            "/api/editor/github/tree?repo=acme/demo&ref=main",
            headers=h,
        )
    assert r.status_code == 400
    assert "Tool Registry" in r.json()["detail"]
    assert r.json().get("entries") is None


def test_propose_pr_creates_approval_no_pr_yet(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={
            "filename": "main.tf",
            "content": 'resource "null_resource" "x" {}\n',
            "source_type": "github",
            "source_repo": "acme/demo",
            "source_path": "infra/main.tf",
            "source_ref": "main",
            "source_sha": "abc123",
        },
    ).json()

    mock_conn = MagicMock()
    mock_conn.get_file_meta = AsyncMock(
        return_value={"content": 'resource "null_resource" "x" {}\n', "sha": "abc123"}
    )
    mock_conn.create_branch = AsyncMock()
    mock_conn.commit_file = AsyncMock()
    mock_conn.create_pull_request = AsyncMock()

    with patch("backend.services.editor_service.try_github_connector_from_context", return_value=mock_conn):
        r = client.post(
            f"/api/editor/files/{created['id']}/propose-pr",
            headers=h,
            json={"title": "Update infra", "base_branch": "main"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["approval_id"]
    assert "diff" in body
    mock_conn.create_branch.assert_not_called()
    mock_conn.create_pull_request.assert_not_called()

    with Session(engine) as session:
        row = session.get(EditorPRApproval, body["approval_id"])
        assert row is not None
        assert row.content == created["content"] or row.content.startswith("resource")


def test_approve_creates_branch_commit_pr_from_db(client, admin_token):
    h = auth_headers(admin_token)
    payload_content = 'resource "aws_s3_bucket" "b" {}\n'
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={
            "filename": "main.tf",
            "content": payload_content,
            "source_type": "github",
            "source_repo": "acme/demo",
            "source_path": "infra/main.tf",
            "source_ref": "main",
            "source_sha": "sha-local",
        },
    ).json()

    mock_conn = MagicMock()
    mock_conn.get_file_meta = AsyncMock(
        return_value={"content": "old\n", "sha": "sha-local"}
    )
    mock_conn.create_branch = AsyncMock(return_value={"ok": True})
    mock_conn.commit_file = AsyncMock(return_value={"ok": True, "sha": "new"})
    mock_conn.create_pull_request = AsyncMock(
        return_value={"ok": True, "html_url": "https://github.com/acme/demo/pull/9", "number": 9}
    )

    with patch("backend.services.editor_service.try_github_connector_from_context", return_value=mock_conn):
        prop = client.post(
            f"/api/editor/files/{created['id']}/propose-pr",
            headers=h,
            json={"title": "Add bucket", "branch_name": "editor/test-branch", "base_branch": "main"},
        ).json()
        # Mutate client-visible content AFTER propose — must not affect commit
        client.put(
            f"/api/editor/files/{created['id']}",
            headers=h,
            json={"content": "CLIENT_TAMPERED\n"},
        )
        approved = client.post(
            f"/api/editor/pr-approvals/{prop['approval_id']}/approve",
            headers=h,
        )
    assert approved.status_code == 200, approved.text
    assert approved.json()["pr_url"] == "https://github.com/acme/demo/pull/9"
    # commit_file must have received DB-frozen content
    args, kwargs = mock_conn.commit_file.await_args
    assert kwargs.get("content") == payload_content or (
        args and payload_content in str(args)
    )
    assert "CLIENT_TAMPERED" not in str(mock_conn.commit_file.await_args)


def test_double_approve_idempotent_one_pr(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={
            "filename": "x.tf",
            "content": "a = 1\n",
            "source_type": "github",
            "source_repo": "acme/demo",
            "source_path": "x.tf",
            "source_ref": "main",
            "source_sha": "s1",
        },
    ).json()
    mock_conn = MagicMock()
    mock_conn.get_file_meta = AsyncMock(return_value={"content": "a = 1\n", "sha": "s1"})
    mock_conn.create_branch = AsyncMock(return_value={"ok": True})
    mock_conn.commit_file = AsyncMock(return_value={"ok": True})
    mock_conn.create_pull_request = AsyncMock(
        return_value={
            "ok": True,
            "html_url": "https://github.com/acme/demo/pull/1",
            "number": 1,
            "reused": False,
        }
    )
    with patch("backend.services.editor_service.try_github_connector_from_context", return_value=mock_conn):
        prop = client.post(
            f"/api/editor/files/{created['id']}/propose-pr",
            headers=h,
            json={"title": "t", "branch_name": "b1", "base_branch": "main"},
        ).json()
        a1 = client.post(f"/api/editor/pr-approvals/{prop['approval_id']}/approve", headers=h)
        a2 = client.post(f"/api/editor/pr-approvals/{prop['approval_id']}/approve", headers=h)
    assert a1.status_code == 200
    assert a2.status_code == 200
    assert a2.json().get("idempotent") is True or a2.json().get("pr_url")
    assert mock_conn.create_pull_request.await_count == 1


def test_moved_base_sha_409(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={
            "filename": "y.tf",
            "content": "y\n",
            "source_type": "github",
            "source_repo": "acme/demo",
            "source_path": "y.tf",
            "source_ref": "main",
            "source_sha": "old-sha",
        },
    ).json()
    mock_conn = MagicMock()
    mock_conn.get_file_meta = AsyncMock(return_value={"content": "upstream\n", "sha": "new-sha"})
    with patch("backend.services.editor_service.try_github_connector_from_context", return_value=mock_conn):
        r = client.post(
            f"/api/editor/files/{created['id']}/propose-pr",
            headers=h,
            json={"title": "t", "base_branch": "main"},
        )
    assert r.status_code == 409
    assert "upstream" in r.json()["detail"].lower() or "changed" in r.json()["detail"].lower()


def test_agent_action_returns_grounding(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/editor/files",
        headers=h,
        json={"filename": "a.py", "content": "print(1)\n"},
    ).json()
    fake = AgentResult(
        agent="code_review_agent",
        status="success",
        summary="Looks fine",
        details={},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by="admin",
        workspace="",
        environment="development",
        grounding="live",
    )
    with patch(
        "backend.pipeline.orchestrator.run_agent_for_workflow",
        new_callable=AsyncMock,
        return_value=fake,
    ):
        r = client.post(
            f"/api/editor/files/{created['id']}/agent-action",
            headers=h,
            json={"action": "review", "selection_start": 0, "selection_end": 8},
        )
    assert r.status_code == 200, r.text
    assert r.json()["grounding"] == "live"


def test_detect_language_from_extension():
    assert detect_language("main.tf") == "hcl"
    assert detect_language("app.yaml") == "yaml"
    assert detect_language("q.sql") == "sql"


def test_idempotency_key_stable():
    a = make_idempotency_key("t", "u", "r", "p", "b", "content")
    b = make_idempotency_key("t", "u", "r", "p", "b", "content")
    assert a == b
