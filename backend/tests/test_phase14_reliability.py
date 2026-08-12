"""Phase 14 — Reliability: webhook delivery idempotency (single side effect)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from sqlmodel import Session, select

from backend.database import engine
from backend.db.models.ops import WebhookDelivery
from backend.rate_limit import limiter
from backend.tests.conftest import auth_headers


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The `client` fixture is module-scoped, so slowapi's in-memory limiter
    (no Redis in the test environment) accumulates request counts across
    every test in this file. Without a reset, whichever test runs later
    inherits quota already spent by an earlier one and gets a spurious 429
    instead of exercising the duplicate-delivery behavior under test."""
    limiter.reset()
    yield


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_duplicate_github_delivery_id_single_incident(client, admin_token, monkeypatch):
    """Same X-GitHub-Delivery → one incident; second call is 200 duplicate."""
    secret = "phase14-gh-webhook-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")

    payload = {
        "action": "completed",
        "workflow_run": {
            "id": 1414,
            "name": "CI",
            "status": "completed",
            "conclusion": "failure",
            "html_url": "https://github.com/acme/beta/actions/runs/1414",
            "head_branch": "main",
            "display_title": "CI",
        },
        "repository": {"full_name": "acme/beta"},
    }
    body = json.dumps(payload).encode()
    delivery = "delivery-phase14-workflow-dup"

    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign(secret, body),
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": delivery,
    }

    r1 = client.post("/api/webhooks/github", content=body, headers=headers)
    assert r1.status_code == 202, r1.text
    assert r1.json()["status"] == "processed"
    incident_id = r1.json()["incident_id"]
    assert incident_id

    r2 = client.post("/api/webhooks/github", content=body, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["incident_id"] == incident_id

    h = auth_headers(admin_token)
    listed = client.get("/api/incidents", headers=h)
    assert listed.status_code == 200
    matches = [i for i in listed.json() if i.get("id") == incident_id]
    assert len(matches) == 1

    # Ledger row exists once
    with Session(engine) as session:
        rows = session.exec(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery)
        ).all()
        assert len(rows) == 1
        assert rows[0].source == "github"


def test_duplicate_inbound_delivery_id_no_second_accept(client, monkeypatch):
    """Inbound gateway: replayed delivery_id returns 200 duplicate after claim."""
    secret = "phase14-inbound-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")

    delivery = "delivery-phase14-inbound-dup"
    envelope = {
        "source": "github",
        "github_event": "pull_request",
        "delivery_id": delivery,
        "payload": {
            "action": "opened",
            "pull_request": {
                "number": 99,
                "title": "Phase14 PR",
                "html_url": "https://github.com/acme/beta/pull/99",
                "user": {"login": "dev"},
            },
            "repository": {"full_name": "acme/beta"},
        },
    }
    body = json.dumps(envelope).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign(secret, body),
    }

    r1 = client.post("/api/webhooks/inbound", content=body, headers=headers)
    assert r1.status_code == 202, r1.text
    data1 = r1.json()
    assert data1.get("status") in {"processed", "accepted"}
    incident_id = data1.get("incident_id")

    r2 = client.post("/api/webhooks/inbound", content=body, headers=headers)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "duplicate"
    assert r2.json()["delivery_id"] == delivery

    with Session(engine) as session:
        rows = session.exec(
            select(WebhookDelivery).where(WebhookDelivery.delivery_id == delivery)
        ).all()
        assert len(rows) == 1

    # If first call created an incident, it remains a single side effect
    if incident_id:
        from backend.db.models.ops import Incident

        with Session(engine) as session:
            count = len(
                session.exec(select(Incident).where(Incident.id == incident_id)).all()
            )
            assert count == 1
