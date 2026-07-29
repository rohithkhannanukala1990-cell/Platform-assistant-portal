"""Phase P2 — API reliability: webhooks, approvals, readiness, pagination."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

from sqlmodel import Session

from backend.database import engine, save_incident, update_incident_status
from backend.db.models.ai_models import AgentRun
from backend.services import readiness as readiness_mod
from backend.services.approval_claim import claim_agent_run, claim_incident_approval
from backend.services.pagination import MAX_PAGE_SIZE, clamp_page
from backend.services.readiness import evaluate_readiness
from backend.services.webhook_delivery import claim_delivery, mark_delivery_status
from backend.tests.conftest import auth_headers


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_duplicate_webhook_delivery_returns_200(client, monkeypatch):
    secret = "p2-webhook-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("ENV", "test")
    delivery = f"p2-deliv-{uuid.uuid4()}"
    body = json.dumps(
        {
            "source": "github",
            "delivery_id": delivery,
            "payload": {"message": "hello"},
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": _sign(secret, body),
        "X-GitHub-Delivery": delivery,
    }
    first = client.post("/api/webhooks/inbound", content=body, headers=headers)
    assert first.status_code == 202, first.text
    second = client.post("/api/webhooks/inbound", content=body, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json().get("status") == "duplicate"


def test_invalid_webhook_signature_is_403_not_500(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "p2-secret")
    monkeypatch.setenv("ENV", "test")
    body = b'{"source":"github","payload":{}}'
    bad = client.post(
        "/api/webhooks/inbound",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=" + ("ab" * 32),
        },
    )
    assert bad.status_code == 403
    assert bad.status_code != 500


def test_empty_alerts_list_does_not_500_in_mapper():
    from backend.routers.webhooks_api import _map_to_cloud_event

    event_type, log_text, _ = _map_to_cloud_event(
        {"alerts": [], "evalMatches": []}, "prometheus"
    )
    assert event_type
    assert "prometheus" in log_text.lower() or "Inbound" in log_text


def test_failed_delivery_can_be_reclaimed():
    did = f"p2-reclaim-{uuid.uuid4()}"
    ok1, _ = claim_delivery(did, "github")
    assert ok1 is True
    mark_delivery_status(did, "error")
    ok2, row = claim_delivery(did, "github")
    assert ok2 is True
    assert row is not None
    assert row.status == "received"


def test_double_approve_agent_run_cas(client, admin_token):
    run_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            AgentRun(
                id=run_id,
                agent="test_agent",
                status="pending_approval",
                summary="p2 double approve",
                environment="development",
                tenant_id="default",
                requires_approval=True,
                approval_payload_json=json.dumps({"commands": []}),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    r1 = client.post(
        f"/api/agents/{run_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert r1.status_code == 200, r1.text
    r2 = client.post(
        f"/api/agents/{run_id}/approve",
        headers=auth_headers(admin_token),
    )
    assert r2.status_code in {400, 409}, r2.text


def test_double_claim_incident_only_one_wins():
    inc = save_incident(
        {
            "severity": "High",
            "summary": "p2 double claim",
            "root_cause": "n/a",
            "evidence": [],
            "action_plan": [],
            "commands": [],
            "raw_logs": "err",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    update_incident_status(inc.id, status="AWAITING_APPROVAL")
    with Session(engine) as s1:
        won1 = claim_incident_approval(s1, inc.id)
    with Session(engine) as s2:
        won2 = claim_incident_approval(s2, inc.id)
    assert won1 is True
    assert won2 is False


def test_ready_endpoint_fails_when_db_down(client, monkeypatch):
    monkeypatch.setenv("ENV", "test")
    with patch.object(
        readiness_mod,
        "check_database",
        return_value={"status": "error", "detail": "database_unavailable"},
    ):
        payload = evaluate_readiness(require_redis=False)
        assert payload["status"] == "not_ready"
        r = client.get("/health/ready")
        # Middleware path uses evaluate_readiness without our patch unless we patch the import site.
    with patch(
        "backend.services.readiness.check_database",
        return_value={"status": "error", "detail": "database_unavailable"},
    ):
        r = client.get("/health/ready")
        assert r.status_code == 503, r.text
        assert r.json().get("status") == "not_ready"
        assert r.json()["checks"]["database"]["status"] == "error"


def test_page_size_cap_enforced():
    assert MAX_PAGE_SIZE == 100
    page, size, offset = clamp_page(1, 999)
    assert size == 100
    assert offset == 0


def test_page_size_query_rejects_over_max(client, admin_token):
    r = client.get(
        "/api/incidents?page=1&page_size=500",
        headers=auth_headers(admin_token),
    )
    # FastAPI Query(le=MAX_PAGE_SIZE) → 422 when over max
    assert r.status_code == 422, r.text


def test_claim_agent_run_second_loses():
    run_id = str(uuid.uuid4())
    with Session(engine) as session:
        session.add(
            AgentRun(
                id=run_id,
                agent="test_agent",
                status="pending_approval",
                summary="cas unit",
                environment="development",
                tenant_id="default",
                requires_approval=True,
                approval_payload_json="{}",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
    with Session(engine) as s1:
        assert claim_agent_run(s1, run_id) is True
    with Session(engine) as s2:
        assert claim_agent_run(s2, run_id) is False
