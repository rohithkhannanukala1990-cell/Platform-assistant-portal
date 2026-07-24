"""Phase 10: GitHub webhooks create incidents (HMAC + delivery idempotency)."""

from __future__ import annotations

import hashlib
import hmac
import json

from backend.tests.conftest import auth_headers


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_github_workflow_failure_creates_incident(client, admin_token, monkeypatch):
    secret = "phase10-gh-webhook-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")

    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 4242,
            "name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/acme/alpha/actions/runs/4242",
            "head_branch": "main",
            "display_title": "CI",
        },
        "repository": {"full_name": "acme/alpha"},
    }
    body = json.dumps(payload).encode()
    delivery = "delivery-phase10-workflow-1"

    r = client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(secret, body),
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": delivery,
        },
    )
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["status"] == "processed"
    assert data["incident_id"]
    incident_id = data["incident_id"]

    # Idempotent replay
    r2 = client.post(
        "/api/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(secret, body),
            "X-GitHub-Event": "workflow_run",
            "X-GitHub-Delivery": delivery,
        },
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["incident_id"] == incident_id

    h = auth_headers(admin_token)
    listed = client.get("/api/incidents", headers=h)
    assert listed.status_code == 200
    incidents = listed.json()
    match = next((i for i in incidents if i.get("id") == incident_id), None)
    assert match is not None
    assert match.get("source") == "github"
    assert "Actions failed" in (match.get("summary") or "") or "CI" in (match.get("summary") or "")


def test_github_pr_opened_via_inbound_creates_incident(client, admin_token, monkeypatch):
    secret = "phase10-gh-inbound-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")

    inner = {
        "action": "opened",
        "pull_request": {
            "number": 12,
            "title": "Add feature",
            "html_url": "https://github.com/acme/alpha/pull/12",
            "user": {"login": "dev"},
        },
        "repository": {"full_name": "acme/alpha"},
    }
    envelope = {
        "source": "github",
        "github_event": "pull_request",
        "delivery_id": "delivery-phase10-pr-1",
        "payload": inner,
    }
    body = json.dumps(envelope).encode()
    r = client.post(
        "/api/webhooks/inbound",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _sign(secret, body),
        },
    )
    assert r.status_code == 202, r.text
    assert r.json().get("incident_id")
    assert r.json().get("status") in {"processed", "accepted"}
