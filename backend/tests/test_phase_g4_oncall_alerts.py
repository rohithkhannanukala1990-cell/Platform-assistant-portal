"""Phase G4 — On-call visibility + rules-based alert correlation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

from sqlmodel import Session

from backend.database import save_incident
from backend.db.core import engine
from backend.db.models.alerts import AlertRule
from backend.observability.metrics import ALERTS_GROUPED_TOTAL, ALERTS_SUPPRESSED_TOTAL
from backend.services.alert_rules import (
    AlertFields,
    evaluate_alert_ingest,
    extract_alert_fields,
    register_grouped_incident,
)
from backend.tests.conftest import auth_headers
from backend.tests.test_phase9_isolation import _login, _make_user


def _create_rule(
    *,
    tenant_id: str = "default",
    name: str = "test-rule",
    action: str = "suppress",
    match_service: str | None = None,
    match_title_regex: str | None = None,
    group_window_sec: int = 0,
    priority: int = 10,
) -> AlertRule:
    rule = AlertRule(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        match_service=match_service,
        match_title_regex=match_title_regex,
        group_window_sec=group_window_sec,
        action=action,
        priority=priority,
        enabled=True,
    )
    with Session(engine) as session:
        session.add(rule)
        session.commit()
        session.refresh(rule)
    return rule


def test_suppress_rule_blocks_ingest(client):
    rule = _create_rule(
        match_service="payment",
        action="suppress",
    )
    before = ALERTS_SUPPRESSED_TOTAL.labels(source="datadog", rule_id=rule.id)._value.get()
    decision = evaluate_alert_ingest(
        tenant_id="default",
        source="datadog",
        log_text="High error rate",
        payload={"service": "payment-api", "severity": "high", "message": "errors"},
    )
    after = ALERTS_SUPPRESSED_TOTAL.labels(source="datadog", rule_id=rule.id)._value.get()
    assert decision.proceed is False
    assert decision.action == "suppress"
    assert decision.rule_id == rule.id
    assert after == before + 1


def test_group_window_attaches_to_existing_incident(client):
    inc = save_incident(
        {
            "severity": "High",
            "summary": "grouped alert",
            "root_cause": "test",
            "evidence": [],
            "action_plan": [],
            "commands": [],
            "raw_logs": "x",
            "model_used": "test",
            "raw_response": "{}",
            "tenant_id": "default",
        }
    )
    rule = _create_rule(
        match_service="checkout",
        action="create_incident",
        group_window_sec=300,
    )
    fields = AlertFields(
        title="checkout timeout",
        service="checkout-service",
        severity="high",
        source="pagerduty",
        log_text="timeout",
    )
    register_grouped_incident(
        tenant_id="default",
        rule_id=rule.id,
        fields=fields,
        incident_id=inc.id,
        group_window_sec=300,
    )
    before = ALERTS_GROUPED_TOTAL.labels(source="pagerduty", rule_id=rule.id)._value.get()
    decision = evaluate_alert_ingest(
        tenant_id="default",
        source="pagerduty",
        log_text="checkout timeout again",
        payload={"service": "checkout-service", "message": "checkout timeout again"},
    )
    after = ALERTS_GROUPED_TOTAL.labels(source="pagerduty", rule_id=rule.id)._value.get()
    assert decision.proceed is False
    assert decision.action == "attach_existing"
    assert decision.incident_id == inc.id
    assert after == before + 1


def test_oncall_now_mock(client, admin_token):
    fake_oncalls = [
        {
            "user": "Alex SRE",
            "schedule": "Primary",
            "schedule_id": "P123",
            "service": "payments",
            "html_url": "https://acme.pagerduty.com/schedules/P123",
        }
    ]
    with patch("backend.routers.oncall.pagerduty_connector_for_user") as mock_pd:
        connector = AsyncMock()
        connector.list_oncalls = AsyncMock(return_value=fake_oncalls)
        mock_pd.return_value = connector
        r = client.get("/api/oncall/now", headers=auth_headers(admin_token))

    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "pagerduty"
    assert "scheduling" in body["scheduling_note"].lower()
    assert "pagerduty" in body["scheduling_note"].lower()
    assert body["oncalls"][0]["user"] == "Alex SRE"
    assert "pagerduty.com" in body["pd_url"]


def test_oncall_requires_auth(client):
    r = client.get("/api/oncall/now")
    assert r.status_code == 401


def test_alert_rules_tenant_isolation(client, admin_token):
    _make_user("g4-owner", tenant_id="tenant-g4-owner", role="Admin")
    _make_user("g4-other", tenant_id="tenant-g4-other", role="Admin")
    token_owner = _login(client, "g4-owner")
    token_other = _login(client, "g4-other")

    create = client.post(
        "/api/alert-rules",
        headers=auth_headers(token_owner),
        json={
            "name": "owner-only",
            "match_service": "billing",
            "action": "suppress",
            "group_window_sec": 0,
            "priority": 1,
        },
    )
    assert create.status_code == 201
    rule_id = create.json()["id"]

    listed_other = client.get("/api/alert-rules", headers=auth_headers(token_other))
    assert listed_other.status_code == 200
    assert all(r["id"] != rule_id for r in listed_other.json())

    delete_other = client.delete(
        f"/api/alert-rules/{rule_id}",
        headers=auth_headers(token_other),
    )
    assert delete_other.status_code == 404


def test_alert_rules_admin_crud(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/alert-rules",
        headers=h,
        json={
            "name": "critical flap",
            "match_title_regex": "CPU.*high",
            "action": "create_incident",
            "group_window_sec": 120,
            "priority": 50,
        },
    )
    assert created.status_code == 201
    rule_id = created.json()["id"]

    listed = client.get("/api/alert-rules", headers=h)
    assert listed.status_code == 200
    assert any(r["id"] == rule_id for r in listed.json())

    deleted = client.delete(f"/api/alert-rules/{rule_id}", headers=h)
    assert deleted.status_code == 204


def test_extract_alert_fields_from_payload():
    fields = extract_alert_fields(
        {"service": "api", "severity": "critical", "message": "disk full"},
        source="datadog",
        log_text="fallback",
    )
    assert fields.service == "api"
    assert fields.severity == "critical"
    assert "disk full" in fields.title
