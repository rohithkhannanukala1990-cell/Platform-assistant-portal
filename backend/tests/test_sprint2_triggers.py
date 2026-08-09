"""Sprint 2: scheduled + event-driven workflow triggers and guardrails."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from backend.auth import AuditLog, engine
from backend.db.models.workflows import WorkflowDefinition, WorkflowRun
from backend.services import workflow_triggers as wt
from backend.services.workflow_engine import start_workflow
from backend.tests.conftest import auth_headers


SIMPLE_STEP = [
    {
        "id": "s1",
        "type": "condition",
        "expression": "1 == 1",
        "depends_on": [],
    }
]

HITL_STEP = [
    {"id": "g", "type": "hitl", "prompt": "approve?", "depends_on": []},
]


@pytest.fixture
def admin_headers(client, admin_token):
    return auth_headers(admin_token)


@pytest.fixture(autouse=True)
def _reset_triggers():
    wt.set_triggers_enabled(True, actor="pytest")
    with wt._queue_lock:
        wt._queued_runs.clear()
    # Prevent cross-test event matching against leftover definitions
    with Session(engine) as session:
        rows = session.exec(
            select(WorkflowDefinition).where(WorkflowDefinition.trigger_type == "event")
        ).all()
        for row in rows:
            row.enabled = False
            session.add(row)
        session.commit()
    yield
    wt.set_triggers_enabled(True, actor="pytest")
    with wt._queue_lock:
        wt._queued_runs.clear()


def _create_workflow(client, headers, **extra):
    body = {
        "name": extra.pop("name", None) or f"trig-{uuid.uuid4().hex[:8]}",
        "description": "sprint2",
        "steps": extra.pop("steps", SIMPLE_STEP),
        "trigger_type": extra.pop("trigger_type", "manual"),
        "trigger_config": extra.pop("trigger_config", {}),
        "enabled": True,
        "risk": "low",
        "max_runs_per_hour": extra.pop("max_runs_per_hour", 100),
        "max_concurrent_runs": extra.pop("max_concurrent_runs", 10),
        "on_concurrent_limit": extra.pop("on_concurrent_limit", "drop"),
        **extra,
    }
    r = client.post("/api/workflows", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _unique_event_config(source: str, **matchers) -> tuple[dict, dict]:
    """Return (trigger_config, payload) bound by a unique marker so tests don't cross-fire."""
    marker = f"t-{uuid.uuid4().hex[:10]}"
    cfg = {"source": source, "marker": marker, **matchers}
    payload = {"source": source, "marker": marker}
    for k, v in matchers.items():
        if k.endswith("_pattern"):
            continue
        if isinstance(v, list) and v:
            payload[k] = v[0]
        else:
            payload[k] = v
    return cfg, payload


def _audit_rows(*, event_type: str, resource_substr: str = "") -> list:
    with Session(engine) as session:
        rows = session.exec(
            select(AuditLog).where(AuditLog.event_type == event_type)
        ).all()
        if resource_substr:
            rows = [r for r in rows if resource_substr in (r.resource or "")]
        return list(rows)


def test_schedule_cron_weekdays_only(client, admin_headers):
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="schedule",
        trigger_config={"cron": "0 9 * * 1-5", "timezone": "UTC"},
    )
    count = wt.reload_schedule_jobs()
    assert count >= 1
    from backend.cron_jobs import scheduler

    job = scheduler.get_job(f"workflow_sched_{wf['id']}")
    assert job is not None
    times = wt.next_fire_times("0 9 * * 1-5", timezone_name="UTC", count=5)
    assert len(times) == 5
    for iso in times:
        dt = datetime.fromisoformat(iso)
        assert dt.weekday() < 5  # Mon-Fri


@pytest.mark.asyncio
async def test_alert_rule_match_fires_bound_workflow(client, admin_headers):
    tenant = "default"
    cfg, payload = _unique_event_config(
        "alert_rule_match",
        severity=["high", "critical"],
        service_pattern="payments.*",
    )
    payload["service"] = "payments-api"
    payload["severity"] = "critical"
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    r = client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)
    assert r.status_code == 200

    started = await wt.fire_event("alert_rule_match", payload, tenant)
    assert len(started) == 1


@pytest.mark.asyncio
async def test_severity_not_in_list_does_not_fire(client, admin_headers):
    cfg, payload = _unique_event_config(
        "alert_rule_match", severity=["high", "critical"]
    )
    payload["severity"] = "low"
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)
    started = await wt.fire_event("alert_rule_match", payload, "default")
    assert started == []


def test_service_pattern_match_and_miss():
    cfg = {"source": "alert_rule_match", "service_pattern": "payments.*"}
    assert wt.match_event_config(
        cfg, {"source": "alert_rule_match", "service": "payments-api"}
    )
    assert not wt.match_event_config(
        cfg, {"source": "alert_rule_match", "service": "billing-api"}
    )


@pytest.mark.asyncio
async def test_rate_limit_13th_run_blocked_with_audit(client, admin_headers):
    cfg, payload = _unique_event_config("incident_created")
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
        max_runs_per_hour=12,
        max_concurrent_runs=50,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)

    # Seed 12 recent runs
    with Session(engine) as session:
        now = datetime.now(timezone.utc)
        for i in range(12):
            session.add(
                WorkflowRun(
                    id=str(uuid.uuid4()),
                    tenant_id="default",
                    workflow_id=wf["id"],
                    status="completed",
                    context_json="{}",
                    steps_state_json="{}",
                    triggered_by="seed",
                    grounding="live",
                    dry_run=False,
                    started_at=now - timedelta(minutes=i),
                    completed_at=now,
                )
            )
        session.commit()

    before = len(_audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"]))
    started = await wt.fire_event("incident_created", payload, "default")
    assert started == []
    after = _audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"])
    assert len(after) > before
    assert any("max_runs_per_hour" in (r.detail or "") for r in after)


@pytest.mark.asyncio
async def test_concurrency_cap_drop(client, admin_headers):
    cfg, payload = _unique_event_config("webhook_inbound")
    wf = _create_workflow(
        client,
        admin_headers,
        steps=HITL_STEP,
        trigger_type="event",
        trigger_config=cfg,
        max_concurrent_runs=1,
        on_concurrent_limit="drop",
        max_runs_per_hour=50,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)

    first = await wt.fire_event("webhook_inbound", payload, "default")
    assert len(first) == 1

    before = len(_audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"]))
    second = await wt.fire_event(
        "webhook_inbound", {**payload, "delivery_id": "d2"}, "default"
    )
    assert second == []
    after = _audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"])
    assert len(after) > before
    assert any("dropped" in (r.detail or "").lower() or "max_concurrent" in (r.detail or "") for r in after)


@pytest.mark.asyncio
async def test_first_automatic_fire_forced_dry_run(client, admin_headers):
    cfg, payload = _unique_event_config("catalog_entity_changed", action="create")
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    assert wf.get("first_live_run_approved_at") is None

    started = await wt.fire_event("catalog_entity_changed", payload, "default")
    assert len(started) == 1
    with Session(engine) as session:
        run = session.get(WorkflowRun, started[0])
        assert run is not None
        assert run.dry_run is True
        ctx = json.loads(run.context_json or "{}")
        assert ctx.get("forced_first_dry_run") is True
        assert run.status == "completed"


@pytest.mark.asyncio
async def test_approve_live_then_live_runs(client, admin_headers):
    cfg, payload = _unique_event_config("incident_created")
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    r = client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)
    assert r.status_code == 200
    assert r.json().get("first_live_run_approved_at")

    started = await wt.fire_event("incident_created", payload, "default")
    assert len(started) == 1
    with Session(engine) as session:
        run = session.get(WorkflowRun, started[0])
        assert run.dry_run is False
        ctx = json.loads(run.context_json or "{}")
        assert not ctx.get("forced_first_dry_run")


def test_steps_json_update_resets_live_approval(client, admin_headers):
    wf = _create_workflow(client, admin_headers, trigger_type="manual")
    r = client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)
    assert r.json().get("first_live_run_approved_at")

    updated_steps = [
        {
            "id": "s1",
            "type": "condition",
            "expression": "2 == 2",
            "depends_on": [],
        }
    ]
    r2 = client.put(
        f"/api/workflows/{wf['id']}",
        headers=admin_headers,
        json={
            "name": wf["name"],
            "description": wf["description"],
            "steps": updated_steps,
            "trigger_type": "manual",
            "trigger_config": {},
            "enabled": True,
            "risk": "low",
            "max_runs_per_hour": 100,
            "max_concurrent_runs": 10,
            "on_concurrent_limit": "drop",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("first_live_run_approved_at") is None


@pytest.mark.asyncio
async def test_kill_switch_stops_automatic_but_manual_works(client, admin_headers):
    cfg, payload = _unique_event_config("alert_rule_match", severity=["critical"])
    payload["severity"] = "critical"
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)

    wt.set_triggers_enabled(False, actor="pytest")
    status = client.get("/api/workflows/triggers/status", headers=admin_headers)
    assert status.status_code == 200
    assert status.json()["triggers_enabled"] is False

    started = await wt.fire_event("alert_rule_match", payload, "default")
    assert started == []

    # Manual run still works
    r = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"dry_run": True, "context": {}},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("id")


@pytest.mark.asyncio
async def test_trigger_depth_4_refused_with_audit(client, admin_headers):
    cfg, payload = _unique_event_config("agent_run_completed")
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)

    before = len(_audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"]))
    started = await wt.fire_event(
        "agent_run_completed",
        payload,
        "default",
        parent_trigger_depth=3,  # → depth 4
    )
    assert started == []
    after = _audit_rows(event_type="workflow_trigger_suppressed", resource_substr=wf["id"])
    assert len(after) > before
    assert any("trigger_depth" in (r.detail or "") for r in after)


@pytest.mark.asyncio
async def test_fire_event_failure_does_not_break_caller(client, admin_headers):
    """safe_fire_event must never raise into the originating request path."""
    with patch.object(wt, "fire_event", new=AsyncMock(side_effect=RuntimeError("boom"))):
        wt.safe_fire_event("incident_created", {"source": "incident_created"}, "default")

    with patch.object(wt, "_start_automatic_run", new=AsyncMock(side_effect=RuntimeError("x"))):
        out = await wt.fire_event(
            "incident_created", {"source": "incident_created"}, "default"
        )
        assert out == []


def test_triggers_status_endpoint(client, admin_headers):
    r = client.get("/api/workflows/triggers/status", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert "triggers_enabled" in body
    assert "scheduled_job_count" in body


@pytest.mark.asyncio
async def test_tenant_isolation_event_does_not_cross(client, admin_headers):
    cfg, payload = _unique_event_config("incident_created")
    wf = _create_workflow(
        client,
        admin_headers,
        trigger_type="event",
        trigger_config=cfg,
    )
    client.post(f"/api/workflows/{wf['id']}/approve-live", headers=admin_headers)
    # Event in another tenant must not start default tenant workflow
    started = await wt.fire_event(
        "incident_created",
        payload,
        "other-tenant",
    )
    assert started == []
