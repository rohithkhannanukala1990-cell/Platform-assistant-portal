"""Sprint 6 — unified approvals inbox: aggregation, filtering, pagination,
approve/reject dispatch, bulk-approve safety, and cross-tenant isolation."""

from __future__ import annotations

import json
import uuid

import pytest
from sqlmodel import Session

from backend.database import AgentRun, engine
from backend.db.models.mcp_models import MCPToolCall
from backend.services.access_service import create_access_request
from backend.services.artifact_service import propose_artifact
from backend.services.change_service import draft_change_record
from backend.services.workflow_engine import start_workflow
from backend.tests.conftest import auth_headers


def _seed_agent_run(tenant_id="default"):
    with Session(engine) as session:
        row = AgentRun(
            id=str(uuid.uuid4()),
            agent="cost_agent",
            task="check spend",
            status="pending_approval",
            summary="Review projected spend increase",
            requires_approval=True,
            environment="production",
            tenant_id=tenant_id,
            triggered_by="tester",
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_mcp_call(tenant_id="default", dangerous=True):
    with Session(engine) as session:
        row = MCPToolCall(
            server_id="srv-1",
            server_name="internal-tools",
            tool_name="delete_resource",
            arguments_json=json.dumps({"id": "abc"}),
            status="pending_approval",
            requires_hitl=True,
            dangerous=dangerous,
            source="api",
            requested_by="tester",
            tenant_id=tenant_id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _seed_entity_action(tenant_id="default"):
    from backend.routers.catalog import CatalogEntity
    from backend.routers.entity_actions import EntityAction, EntityActionRun

    with Session(engine) as session:
        entity = CatalogEntity(
            name=f"svc-{uuid.uuid4().hex[:6]}",
            kind="Service",
            lifecycle="production",
            owner_team="platform",
            tenant_id=tenant_id,
        )
        session.add(entity)
        session.flush()
        action = EntityAction(name="Request prod access", slug=f"req-{uuid.uuid4().hex[:6]}")
        session.add(action)
        session.flush()
        run = EntityActionRun(
            action_id=action.id,
            entity_id=entity.id,
            requested_by="tester",
            status="pending",
        )
        session.add(run)
        session.commit()
        return run.id


def _inbox(client, headers, **params):
    res = client.get("/api/approvals/inbox", headers=headers, params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _find(items, item_id):
    return next((i for i in items if i["id"] == item_id), None)


def test_every_source_appears_in_inbox(client, admin_token):
    h = auth_headers(admin_token)
    agent_id = _seed_agent_run()
    mcp_id = _seed_mcp_call()
    entity_run_id = _seed_entity_action()
    access_row = create_access_request(
        tenant_id="default",
        workspace_id=None,
        requester="tester",
        subject="new.hire",
        resource_type="unmapped_resource_type",
        resource_id="res-1",
        justification="onboarding",
    )
    change_row = draft_change_record(
        tenant_id="default",
        workspace_id=None,
        change_type="deploy",
        source_run_id=None,
        source_artifact_id=None,
        title="Deploy payments v2",
        description="Roll out payments v2",
    )

    data = _inbox(client, h, page_size=100)
    ids = {i["id"] for i in data["items"]}

    assert f"agent:{agent_id}" in ids
    assert f"mcp:{mcp_id}" in ids
    assert f"entity_action:{entity_run_id}" in ids
    assert f"access:{access_row.id}" in ids
    assert f"change:{change_row.id}" in ids

    sources = {i["id"]: i["source"] for i in data["items"]}
    assert sources[f"agent:{agent_id}"] == "agent"
    assert sources[f"mcp:{mcp_id}"] == "mcp"
    assert sources[f"entity_action:{entity_run_id}"] == "entity_action"
    assert sources[f"access:{access_row.id}"] == "access"
    assert sources[f"change:{change_row.id}"] == "change"


@pytest.mark.asyncio
async def test_workflow_hitl_gate_appears_and_approves_via_inbox(client, admin_token):
    h = auth_headers(admin_token)
    wf = client.post(
        "/api/workflows",
        headers=h,
        json={
            "name": f"inbox-test-wf-{uuid.uuid4().hex[:6]}",
            "steps": [{"id": "s1", "type": "hitl", "prompt": "Approve this?", "depends_on": []}],
            "trigger_type": "manual",
        },
    )
    assert wf.status_code == 201, wf.text
    wf_id = wf.json()["id"]

    run = await start_workflow(wf_id, "default", "tester", {}, dry_run=False)
    assert run.status == "pending_approval"
    item_id = f"workflow:{run.id}"

    data = _inbox(client, h, source="workflow", page_size=100)
    item = _find(data["items"], item_id)
    assert item is not None
    assert item["source"] == "workflow"

    approve = client.post(f"/api/approvals/{item_id}/approve", headers=h, json={})
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "completed"

    data_after = _inbox(client, h, source="workflow", page_size=100)
    assert _find(data_after["items"], item_id) is None


def test_access_request_approves_via_inbox_and_uses_provision_path(client, admin_token):
    h = auth_headers(admin_token)
    row = create_access_request(
        tenant_id="default",
        workspace_id=None,
        requester="tester",
        subject="new.hire2",
        resource_type="unmapped_resource_type",
        resource_id="res-2",
        justification="onboarding",
    )
    item_id = f"access:{row.id}"

    approve = client.post(f"/api/approvals/{item_id}/approve", headers=h, json={})
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["ok"] is True
    assert body.get("note") == "no connector mapped — logical grant only"

    from backend.db.models.access import AccessRequestRecord

    with Session(engine) as session:
        refreshed = session.get(AccessRequestRecord, row.id)
        assert refreshed.status == "provisioned"


def test_inbox_filtering_and_pagination(client, admin_token):
    h = auth_headers(admin_token)
    for _ in range(3):
        _seed_mcp_call()

    all_items = _inbox(client, h, source="mcp", page_size=100)["items"]
    assert len(all_items) >= 3

    page1 = _inbox(client, h, source="mcp", page=1, page_size=2)
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2
    assert page1["total"] >= 3

    high_risk = _inbox(client, h, source="mcp", risk="high", page_size=100)["items"]
    assert all(i["risk"] == "high" for i in high_risk)
    assert len(high_risk) >= 3  # every seeded MCP call above is dangerous=True


def test_bulk_approve_refuses_typed_confirmation_item(client, admin_token):
    h = auth_headers(admin_token)
    approval = propose_artifact(
        tenant_id="default",
        username="tester",
        agent="deploy_agent",
        connector="terraform",
        method="apply_plan",
        params={"workspace": "prod-critical"},
        preview={"require_typed_confirm": True, "confirm_phrase": "prod-critical"},
        grounding="live",
        summary="Destroy 3 resources",
    )
    item_id = f"agent:{approval['agent_run_id']}"

    data = _inbox(client, h, page_size=100)
    item = _find(data["items"], item_id)
    assert item is not None
    assert item["needs_typed_confirmation"] is True

    bulk = client.post("/api/approvals/bulk-approve", headers=h, json={"ids": [item_id]})
    assert bulk.status_code == 200, bulk.text
    results = bulk.json()["results"]
    assert results[0]["ok"] is False

    with Session(engine) as session:
        refreshed = session.get(AgentRun, approval["agent_run_id"])
        assert refreshed.status == "pending_approval"


def test_bulk_approve_refuses_dual_approver_item(client, admin_token):
    h = auth_headers(admin_token)
    approval = propose_artifact(
        tenant_id="default",
        username="tester",
        agent="deploy_agent",
        connector="sql",
        method="execute_migration",
        params={"forward_sql": "ALTER TABLE x DROP COLUMN y"},
        preview={},
        grounding="live",
        summary="Destructive migration",
        approvals_required=2,
    )
    item_id = f"agent:{approval['agent_run_id']}"

    data = _inbox(client, h, page_size=100)
    item = _find(data["items"], item_id)
    assert item is not None
    assert item["needs_second_approver"] is True

    bulk = client.post("/api/approvals/bulk-approve", headers=h, json={"ids": [item_id]})
    assert bulk.status_code == 200, bulk.text
    assert bulk.json()["results"][0]["ok"] is False


def test_cross_tenant_items_never_appear(client, admin_token):
    h = auth_headers(admin_token)
    other_id = _seed_mcp_call(tenant_id="other-tenant")

    data = _inbox(client, h, source="mcp", page_size=100)
    ids = {i["id"] for i in data["items"]}
    assert f"mcp:{other_id}" not in ids
