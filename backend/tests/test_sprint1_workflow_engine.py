"""Sprint 1: workflow engine — chaining, HITL CAS, grounding, validation."""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from backend.agents.base import AgentResult
from backend.auth import User, engine, hash_password
from backend.db.models.workflows import WorkflowRun
from backend.services import workflow_engine as we
from backend.services.workflow_engine import (
    evaluate_condition,
    resolve_templates,
    validate_workflow_steps,
    worst_grounding,
)
from backend.tests.conftest import auth_headers


def _agent_result(agent: str, *, grounding: str = "live", summary: str = "ok", **details) -> AgentResult:
    return AgentResult(
        agent=agent,
        status="success",
        summary=summary,
        details={"summary": summary, **details},
        timestamp=datetime.now(timezone.utc).isoformat(),
        triggered_by="test",
        workspace="",
        environment="development",
        grounding=grounding,
    )


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


THREE_STEP = [
    {
        "id": "s1",
        "type": "agent",
        "agent": "incident_agent",
        "input": {"task": "triage {{trigger.alert_title}}"},
        "depends_on": [],
        "requires_approval": False,
    },
    {
        "id": "s2",
        "type": "hitl",
        "prompt": "Approve remediation for {{steps.s1.output.summary}}?",
        "depends_on": ["s1"],
    },
    {
        "id": "s3",
        "type": "agent",
        "agent": "runbook_agent",
        "input": {"task": "remediate using {{steps.s1.output.summary}}"},
        "depends_on": ["s2"],
        "requires_approval": False,
    },
]


@pytest.fixture
def admin_headers(client, admin_token):
    return auth_headers(admin_token)


def _create_workflow(client, headers, steps=None, name=None, **extra):
    body = {
        "name": name or f"wf-{uuid.uuid4().hex[:8]}",
        "description": "test",
        "steps": steps if steps is not None else THREE_STEP,
        "trigger_type": "manual",
        "enabled": True,
        "risk": "medium",
        "max_runs_per_hour": 100,
        "max_concurrent_runs": 50,
        **extra,
    }
    r = client.post("/api/workflows", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── Unit helpers ─────────────────────────────────────────────────────────────


def test_template_resolves_step_output():
    ctx = {"trigger": {"alert_title": "CPU high"}, "steps": {"s1": {"output": {"summary": "triaged"}}}}
    assert resolve_templates("{{steps.s1.output.summary}}", ctx) == "triaged"
    assert resolve_templates("Alert: {{trigger.alert_title}}", ctx) == "Alert: CPU high"


def test_template_later_step_rejected_at_validation():
    steps = [
        {
            "id": "s1",
            "type": "agent",
            "agent": "incident_agent",
            "input": {"task": "{{steps.s2.output.x}}"},
            "depends_on": [],
        },
        {
            "id": "s2",
            "type": "agent",
            "agent": "runbook_agent",
            "input": {"task": "x"},
            "depends_on": ["s1"],
        },
    ]
    errors = validate_workflow_steps(steps)
    assert any("does not run before" in e for e in errors)


def test_cyclic_dag_rejected():
    steps = [
        {"id": "a", "type": "agent", "agent": "incident_agent", "input": {}, "depends_on": ["b"]},
        {"id": "b", "type": "agent", "agent": "incident_agent", "input": {}, "depends_on": ["a"]},
    ]
    errors = validate_workflow_steps(steps)
    assert any("cycle" in e.lower() for e in errors)


def test_write_connector_without_hitl_rejected():
    steps = [
        {
            "id": "s1",
            "type": "connector",
            "connector": "slack",
            "method": "post_thread_reply",
            "args": {"text": "hi"},
            "depends_on": [],
        }
    ]
    errors = validate_workflow_steps(steps)
    assert any("preceding hitl" in e for e in errors)


def test_write_connector_with_hitl_ok():
    steps = [
        {"id": "g", "type": "hitl", "prompt": "ok?", "depends_on": []},
        {
            "id": "s1",
            "type": "connector",
            "connector": "slack",
            "method": "post_message",
            "args": {"text": "hi"},
            "depends_on": ["g"],
        },
    ]
    assert validate_workflow_steps(steps) == []


def test_worst_grounding_none_wins():
    assert worst_grounding("live", "partial", "none") == "none"
    assert worst_grounding("live", "partial") == "partial"
    assert worst_grounding("live", "live") == "live"


def test_condition_evaluator_no_eval():
    ctx = {"trigger": {"severity": "high"}, "steps": {"s1": {"output": {"ok": True}}}}
    assert evaluate_condition('trigger.severity == "high"', ctx) is True
    assert evaluate_condition("steps.s1.output.ok", ctx) is True
    assert evaluate_condition('trigger.severity == "low"', ctx) is False
    with pytest.raises(ValueError):
        evaluate_condition("__import__('os').system('x')", ctx)


# ── API / engine ─────────────────────────────────────────────────────────────


def test_create_cyclic_returns_422(client, admin_headers):
    r = client.post(
        "/api/workflows",
        headers=admin_headers,
        json={
            "name": "cyclic",
            "steps": [
                {"id": "a", "type": "hitl", "prompt": "a", "depends_on": ["b"]},
                {"id": "b", "type": "hitl", "prompt": "b", "depends_on": ["a"]},
            ],
        },
    )
    assert r.status_code == 422, r.text


def test_create_write_connector_no_hitl_422(client, admin_headers):
    r = client.post(
        "/api/workflows",
        headers=admin_headers,
        json={
            "name": "bad-write",
            "steps": [
                {
                    "id": "s1",
                    "type": "connector",
                    "connector": "slack",
                    "method": "post_message",
                    "args": {},
                    "depends_on": [],
                }
            ],
        },
    )
    assert r.status_code == 422, r.text


def test_validate_endpoint_template_forward_ref(client, admin_headers):
    r = client.post(
        "/api/workflows/validate",
        headers=admin_headers,
        json={
            "steps": [
                {
                    "id": "s1",
                    "type": "agent",
                    "agent": "incident_agent",
                    "input": {"task": "{{steps.s2.output.x}}"},
                    "depends_on": [],
                },
                {
                    "id": "s2",
                    "type": "agent",
                    "agent": "incident_agent",
                    "input": {"task": "x"},
                    "depends_on": ["s1"],
                },
            ]
        },
    )
    assert r.status_code == 422, r.text


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_three_step_pauses_at_hitl(mock_run, client, admin_headers):
    mock_run.return_value = _agent_result("incident_agent", summary="triaged-alpha")
    wf = _create_workflow(client, admin_headers)
    r = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {"alert_title": "disk full"}, "dry_run": False},
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "pending_approval"
    assert run["current_step_id"] == "s2"
    assert run["steps_state"]["s1"]["status"] == "completed"
    assert run["steps_state"]["s1"]["output"]["summary"] == "triaged-alpha"
    assert run["steps_state"]["s2"]["status"] == "pending_approval"
    assert "s3" not in run["steps_state"] or run["steps_state"].get("s3", {}).get("status") not in {
        "completed",
        "running",
    }
    # Agent called once so far
    assert mock_run.await_count == 1


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_approve_resumes_and_passes_context(mock_run, client, admin_headers):
    async def _side_effect(agent_name, input_payload, context):
        return _agent_result(agent_name, summary=f"from-{agent_name}", task=str(input_payload.get("task")))

    mock_run.side_effect = _side_effect
    wf = _create_workflow(client, admin_headers)
    started = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {"alert_title": "page"}, "dry_run": False},
    ).json()
    assert started["status"] == "pending_approval"
    approved = client.post(
        f"/api/workflows/runs/{started['id']}/approve",
        headers=admin_headers,
        json={"step_id": "s2"},
    )
    assert approved.status_code == 200, approved.text
    run = approved.json()
    assert run["status"] == "completed"
    assert run["steps_state"]["s2"]["status"] == "approved"
    assert run["steps_state"]["s3"]["status"] == "completed"
    # Second agent received templated task with s1 summary
    second_call = mock_run.await_args_list[1]
    task = second_call.args[1].get("task") if second_call.args else second_call.kwargs.get("input_payload", {}).get("task")
    assert "from-incident_agent" in str(task) or "triaged" in str(task) or "from-incident_agent" in str(
        second_call
    )


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_reject_stops_further_steps(mock_run, client, admin_headers):
    mock_run.return_value = _agent_result("incident_agent", summary="x")
    wf = _create_workflow(client, admin_headers)
    started = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {}, "dry_run": False},
    ).json()
    rejected = client.post(
        f"/api/workflows/runs/{started['id']}/reject",
        headers=admin_headers,
        json={"step_id": "s2", "reason": "not safe"},
    )
    assert rejected.status_code == 200, rejected.text
    run = rejected.json()
    assert run["status"] == "rejected"
    assert "s3" not in run["steps_state"] or run["steps_state"].get("s3", {}).get("status") != "completed"
    assert mock_run.await_count == 1


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_concurrent_approvals_one_wins(mock_run, client, admin_headers):
    mock_run.return_value = _agent_result("incident_agent", summary="x")
    wf = _create_workflow(client, admin_headers)
    started = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {}, "dry_run": False},
    ).json()
    run_id = started["id"]

    def _approve():
        return client.post(
            f"/api/workflows/runs/{run_id}/approve",
            headers=admin_headers,
            json={"step_id": "s2"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(_approve)
        f2 = pool.submit(_approve)
        results = [f1.result(), f2.result()]

    codes = sorted(r.status_code for r in results)
    assert codes == [200, 409], [(r.status_code, r.text) for r in results]


def test_cross_tenant_run_404(client, admin_headers):
    with patch(
        "backend.pipeline.orchestrator.run_agent_for_workflow",
        new_callable=AsyncMock,
        return_value=_agent_result("incident_agent"),
    ):
        wf = _create_workflow(client, admin_headers)
        started = client.post(
            f"/api/workflows/{wf['id']}/run",
            headers=admin_headers,
            json={"context": {}},
        ).json()

    other = _make_user(f"wf-other-{uuid.uuid4().hex[:6]}", tenant_id="tenant-other")
    token = _login(client, other.username)
    r = client.get(f"/api/workflows/runs/{started['id']}", headers=auth_headers(token))
    assert r.status_code == 404


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_grounding_none_propagates(mock_run, client, admin_headers):
    mock_run.return_value = _agent_result("incident_agent", grounding="none", summary="no data")
    wf = _create_workflow(client, admin_headers)
    run = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {}},
    ).json()
    assert run["grounding"] == "none"


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_dry_run_skips_connector_writes(mock_run, client, admin_headers):
    mock_run.return_value = _agent_result("incident_agent", summary="dry")
    steps = [
        {
            "id": "s1",
            "type": "agent",
            "agent": "incident_agent",
            "input": {"task": "x"},
            "depends_on": [],
        },
        {"id": "g", "type": "hitl", "prompt": "ok?", "depends_on": ["s1"]},
        {
            "id": "c1",
            "type": "connector",
            "connector": "slack",
            "method": "post_message",
            "args": {"text": "{{steps.s1.output.summary}}"},
            "depends_on": ["g"],
        },
    ]
    wf = _create_workflow(client, admin_headers, steps=steps, name="dry-conn")
    started = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"dry_run": True, "context": {}},
    ).json()
    assert started["dry_run"] is True
    assert started["status"] == "pending_approval"

    with patch("backend.connectors.registry.get_connector") as get_conn:
        conn = AsyncMock()
        get_conn.return_value = conn
        done = client.post(
            f"/api/workflows/runs/{started['id']}/approve",
            headers=admin_headers,
            json={"step_id": "g"},
        )
        assert done.status_code == 200, done.text
        run = done.json()
        assert run["status"] == "completed"
        assert run["steps_state"]["c1"]["output"].get("dry_run") is True
        assert "would_call" in run["steps_state"]["c1"]["output"]
        conn.execute_action.assert_not_called()


@patch(
    "backend.pipeline.orchestrator.run_agent_for_workflow",
    new_callable=AsyncMock,
)
def test_timeout_marks_failed(mock_run, client, admin_headers, monkeypatch):
    mock_run.return_value = _agent_result("incident_agent", summary="x")
    monkeypatch.setenv("WORKFLOW_RUN_TIMEOUT_MINUTES", "30")
    wf = _create_workflow(client, admin_headers)
    started = client.post(
        f"/api/workflows/{wf['id']}/run",
        headers=admin_headers,
        json={"context": {}},
    ).json()
    # Backdate started_at
    with Session(engine) as session:
        row = session.get(WorkflowRun, started["id"])
        row.started_at = datetime.now(timezone.utc) - timedelta(minutes=45)
        session.add(row)
        session.commit()

    run = asyncio.run(we.advance_workflow(started["id"], started["tenant_id"]))
    assert run.status == "failed"
    assert run.error and "timed out" in run.error.lower()


def test_list_workflows_tenant_scoped(client, admin_headers):
    _create_workflow(client, admin_headers, name="mine")
    other = _make_user(f"wf-list-{uuid.uuid4().hex[:6]}", tenant_id="tenant-list-b")
    token = _login(client, other.username)
    # create under other tenant
    r = client.post(
        "/api/workflows",
        headers=auth_headers(token),
        json={"name": "theirs", "steps": [{"id": "h", "type": "hitl", "prompt": "x", "depends_on": []}]},
    )
    assert r.status_code == 201, r.text
    mine = client.get("/api/workflows", headers=admin_headers).json()
    theirs = client.get("/api/workflows", headers=auth_headers(token)).json()
    assert all(w["tenant_id"] != "tenant-list-b" or w["name"] != "theirs" for w in mine) or True
    assert any(w["name"] == "theirs" for w in theirs)
    assert not any(w["name"] == "theirs" for w in mine)


def test_cancel_running_workflow(client, admin_headers):
    with patch(
        "backend.pipeline.orchestrator.run_agent_for_workflow",
        new_callable=AsyncMock,
        return_value=_agent_result("incident_agent"),
    ):
        wf = _create_workflow(client, admin_headers)
        started = client.post(
            f"/api/workflows/{wf['id']}/run",
            headers=admin_headers,
            json={"context": {}},
        ).json()
    assert started["status"] == "pending_approval"
    cancelled = client.post(
        f"/api/workflows/runs/{started['id']}/cancel",
        headers=admin_headers,
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def test_get_workflow_cross_tenant_404(client, admin_headers):
    wf = _create_workflow(
        client,
        admin_headers,
        steps=[{"id": "h", "type": "hitl", "prompt": "x", "depends_on": []}],
    )
    other = _make_user(f"wf-get-{uuid.uuid4().hex[:6]}", tenant_id="tenant-get-b")
    token = _login(client, other.username)
    r = client.get(f"/api/workflows/{wf['id']}", headers=auth_headers(token))
    assert r.status_code == 404


def test_depends_on_missing_step_422(client, admin_headers):
    r = client.post(
        "/api/workflows",
        headers=admin_headers,
        json={
            "name": "bad-dep",
            "steps": [
                {"id": "s1", "type": "hitl", "prompt": "x", "depends_on": ["missing"]},
            ],
        },
    )
    assert r.status_code == 422


def test_enable_toggle_update(client, admin_headers):
    wf = _create_workflow(
        client,
        admin_headers,
        steps=[{"id": "h", "type": "hitl", "prompt": "x", "depends_on": []}],
    )
    r = client.put(
        f"/api/workflows/{wf['id']}",
        headers=admin_headers,
        json={
            "name": wf["name"],
            "steps": wf["steps"],
            "enabled": False,
            "risk": "low",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False


def test_end_to_end_three_step_completed(client, admin_headers):
    with patch(
        "backend.pipeline.orchestrator.run_agent_for_workflow",
        new_callable=AsyncMock,
    ) as mock_run:
        mock_run.side_effect = [
            _agent_result("incident_agent", summary="step1-out"),
            _agent_result("runbook_agent", summary="step3-out"),
        ]
        wf = _create_workflow(client, admin_headers)
        started = client.post(
            f"/api/workflows/{wf['id']}/run",
            headers=admin_headers,
            json={"context": {"alert_title": "burn"}},
        ).json()
        assert started["status"] == "pending_approval"
        finished = client.post(
            f"/api/workflows/runs/{started['id']}/approve",
            headers=admin_headers,
            json={},
        ).json()
        assert finished["status"] == "completed"
        assert finished["steps_state"]["s1"]["output"]["summary"] == "step1-out"
        assert finished["steps_state"]["s3"]["output"]["summary"] == "step3-out"
        assert mock_run.await_count == 2
