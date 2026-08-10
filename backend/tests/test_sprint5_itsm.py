"""Sprint 5: access provisioning, change management, compliance evidence."""

from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.context import PlatformContext
from backend.db.models.policy import CommandPolicyRule
from backend.mcp.portal_tools import WRITE_TOOLS
from backend.services.artifact_service import (
    ArtifactApproval,
    fulfill_artifact_approval,
    propose_artifact,
)


REQUIRED_APPROVAL_NAMES = [
    "approval-okta-add-user-to-group",
    "approval-okta-remove-user-from-group",
    "approval-okta-deactivate-user",
    "approval-compliance-evidence-pack",
]

REQUIRED_WRITE_TOOLS = {
    "portal_okta_add_user_to_group",
    "portal_okta_remove_user_from_group",
    "portal_okta_deactivate_user",
    "portal_compliance_generate_evidence_pack",
}


def _ctx(user="admin", tenant_id="default"):
    return PlatformContext(
        user_id=user,
        user_role="Admin",
        tenant_id=tenant_id,
        environment="development",
    )


def _admin(session: Session) -> User:
    u = session.exec(select(User).where(User.username == "admin")).first()
    assert u
    return u


# ── Policy / WRITE_TOOLS ──────────────────────────────────────────────────────


def test_sprint5_policy_and_write_tools(client):
    from backend.db.core import _seed_github_editor_policy

    _seed_github_editor_policy()
    with Session(engine) as session:
        names = {
            r.name
            for r in session.exec(select(CommandPolicyRule)).all()
            if r.effect == "require_approval"
        }
    for name in REQUIRED_APPROVAL_NAMES:
        assert name in names, f"missing policy rule {name}"
    missing = REQUIRED_WRITE_TOOLS - WRITE_TOOLS
    assert not missing, f"missing WRITE_TOOLS: {missing}"


# ── Access agent ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_access_routes_to_registered_owner(client):
    from backend.agents.access_agent import access_agent
    from backend.db.models.access import AccessRequestRecord, ResourceOwner

    tenant = "default"
    resource_id = f"payments-team-{os.getpid()}"
    with Session(engine) as db:
        db.add(
            ResourceOwner(
                tenant_id=tenant,
                resource_type="github_team",
                resource_id=resource_id,
                resource_name="payments",
                owner_username="alice",
            )
        )
        db.commit()

    with Session(engine) as db:
        result = await access_agent.run(
            {
                "action": "propose_provisioning",
                "resource_type": "github_team",
                "resource_id": resource_id,
                "subject_username": "bob",
                "justification": "onboarding",
            },
            _ctx(user="bob"),
            db,
        )
    assert result.status == "pending_approval"
    req_id = result.details["access_request_id"]
    with Session(engine) as db:
        row = db.get(AccessRequestRecord, req_id)
        assert row.owner_username == "alice"
        assert row.owner_missing is False


@pytest.mark.asyncio
async def test_access_falls_back_to_admin_when_no_owner(client):
    from backend.agents.access_agent import access_agent
    from backend.db.models.access import AccessRequestRecord

    with Session(engine) as db:
        result = await access_agent.run(
            {
                "action": "propose_provisioning",
                "resource_type": "github_team",
                "resource_id": f"unowned-{os.getpid()}",
                "subject_username": "bob",
            },
            _ctx(user="bob"),
            db,
        )
    assert result.status == "pending_approval"
    req_id = result.details["access_request_id"]
    with Session(engine) as db:
        row = db.get(AccessRequestRecord, req_id)
        assert row.owner_username == "admin"
        assert row.owner_missing is True
    assert "NO OWNER REGISTERED" in result.summary


def test_check_policy_flags_broader_access(client):
    from backend.agents.access_agent import check_policy
    from backend.db.models.access import AccessRequestRecord

    tenant = "default"
    rid = f"broad-{os.getpid()}"
    with Session(engine) as db:
        db.add(
            AccessRequestRecord(
                tenant_id=tenant,
                requester_username="bob",
                subject_username="bob",
                resource_type="okta_group",
                resource_id=rid,
                resource_name=rid,
                owner_username="alice",
                status="provisioned",
                connector="okta",
                connector_method="add_user_to_group",
            )
        )
        db.add(
            AccessRequestRecord(
                tenant_id=tenant,
                requester_username="bob",
                subject_username="bob",
                resource_type="okta_group",
                resource_id=f"other-{os.getpid()}",
                resource_name="other",
                owner_username="alice",
                status="provisioned",
                connector="okta",
                connector_method="add_user_to_group",
            )
        )
        db.commit()
        assessment = check_policy(
            db,
            tenant_id=tenant,
            subject_username="bob",
            resource_type="okta_group",
            resource_id=f"new-{os.getpid()}",
        )
    reasoning = " ".join(assessment.get("reasoning") or [])
    assert "already has" in reasoning
    assert assessment.get("recommendation") == "review_broad_access"


@pytest.mark.asyncio
async def test_provisioning_calls_correct_connector_method(client):
    from backend.db.models.access import AccessRequestRecord, ResourceOwner
    from backend.services.access_service import (
        create_access_request,
        provision_access_request,
    )

    rid = f"okta-grp-{os.getpid()}"
    with Session(engine) as db:
        db.add(
            ResourceOwner(
                tenant_id="default",
                resource_type="okta_group",
                resource_id=rid,
                owner_username="alice",
            )
        )
        db.commit()

    row = create_access_request(
        tenant_id="default",
        workspace_id=None,
        requester="bob",
        subject="bob",
        resource_type="okta_group",
        resource_id=rid,
        duration_hours=2,
    )

    seen = {}

    async def _fake_call(*, connector, method, params, idempotency_key):
        seen["connector"] = connector
        seen["method"] = method
        seen["params"] = params
        return {"ok": True}

    with Session(engine) as session:
        admin = _admin(session)
    result = await provision_access_request(
        request_id=row.id,
        tenant_id="default",
        approver="admin",
        user=admin,
        connector_call=_fake_call,
    )
    assert result.get("ok")
    assert seen["connector"] == "okta"
    assert seen["method"] == "add_user_to_group"
    with Session(engine) as db:
        live = db.get(AccessRequestRecord, row.id)
        assert live.status == "provisioned"
        assert live.expires_at is not None
        # expires_at ~= now + 2h — sqlite returns tz-naive datetimes; strip.
        exp = live.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = (exp - datetime.now(timezone.utc)).total_seconds()
        assert 3500 < delta < 7300


@pytest.mark.asyncio
async def test_expiry_sweep_revokes_and_warns(client):
    from backend.db.models.access import AccessRequestRecord
    from backend.services.access_service import run_expiry_sweep

    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        expired = AccessRequestRecord(
            tenant_id="default",
            requester_username="bob",
            subject_username="bob",
            resource_type="okta_group",
            resource_id=f"exp-{os.getpid()}",
            resource_name="exp",
            owner_username="alice",
            status="provisioned",
            connector="okta",
            connector_method="add_user_to_group",
            connector_params_json=json.dumps(
                {"resource_type": "okta_group", "resource_id": "x", "subject_username": "bob"}
            ),
            duration_hours=1,
            provisioned_at=now - timedelta(hours=2),
            expires_at=now - timedelta(minutes=5),
        )
        db.add(expired)
        soon = AccessRequestRecord(
            tenant_id="default",
            requester_username="bob",
            subject_username="bob",
            resource_type="okta_group",
            resource_id=f"soon-{os.getpid()}",
            resource_name="soon",
            owner_username="alice",
            status="provisioned",
            connector="okta",
            connector_method="add_user_to_group",
            connector_params_json="{}",
            duration_hours=1,
            provisioned_at=now - timedelta(minutes=30),
            expires_at=now + timedelta(minutes=45),
        )
        db.add(soon)
        db.commit()
        db.refresh(expired)
        db.refresh(soon)
        expired_id = expired.id
        soon_id = soon.id

    async def _dummy_write(**kwargs):
        return {"ok": True}

    with patch(
        "backend.services.artifact_service._execute_connector_write",
        new=_dummy_write,
    ):
        result = await run_expiry_sweep()
    assert result["revoked"] >= 1
    assert result["warned"] >= 1

    with Session(engine) as db:
        exp = db.get(AccessRequestRecord, expired_id)
        assert exp.status == "expired"
        assert exp.revoked_at is not None
        soon2 = db.get(AccessRequestRecord, soon_id)
        assert soon2.warning_sent_at is not None
        assert soon2.status == "provisioned"


@pytest.mark.asyncio
async def test_expiry_revocation_requires_no_approval(client):
    """Revoke path must not create an ArtifactApproval and must not raise."""
    from backend.db.models.access import AccessRequestRecord
    from backend.services.access_service import revoke_access_request

    with Session(engine) as db:
        row = AccessRequestRecord(
            tenant_id="default",
            requester_username="bob",
            subject_username="bob",
            resource_type="okta_group",
            resource_id=f"rev-{os.getpid()}",
            resource_name="rev",
            owner_username="alice",
            status="provisioned",
            connector="okta",
            connector_method="add_user_to_group",
            connector_params_json="{}",
            duration_hours=1,
            provisioned_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        row_id = row.id
        admin = _admin(db)

    async def _fake_call(*, connector, method, params, idempotency_key):
        return {"ok": True}

    result = await revoke_access_request(
        request_id=row_id,
        tenant_id="default",
        actor="system",
        user=admin,
        reason="expired",
        connector_call=_fake_call,
    )
    assert result["ok"]
    with Session(engine) as db:
        # No ArtifactApproval was created for this revoke path
        approvals = db.exec(
            select(ArtifactApproval).where(
                ArtifactApproval.method == "remove_user_from_group",
                ArtifactApproval.tenant_id == "default",
            )
        ).all()
        # Approvals could exist from other tests, but idempotency ledger for this
        # revoke should not have created a new pending approval:
        for a in approvals:
            params = json.loads(a.params_json or "{}")
            assert (
                params.get("resource_id") != row_id
            ), "revoke must not create a pending approval"


@pytest.mark.asyncio
async def test_missing_okta_returns_no_data(client):
    from backend.agents.access_agent import access_agent

    with patch.object(access_agent, "_ground_okta", AsyncMock(return_value=None)):
        with Session(engine) as db:
            result = await access_agent.run(
                {
                    "action": "propose_provisioning",
                    "resource_type": "okta_group",
                    "resource_id": f"missing-{os.getpid()}",
                    "subject_username": "bob",
                },
                _ctx(),
                db,
            )
    assert result.status == "skipped"
    assert result.details.get("reason") == "no_data"


# ── Change agent ──────────────────────────────────────────────────────────────


def test_change_drafts_and_tier1_is_high_risk(client):
    from backend.db.models.access import ChangeRecord
    from backend.services.change_service import draft_change_record

    record = draft_change_record(
        tenant_id="default",
        workspace_id=None,
        change_type="deploy",
        source_run_id="run-1",
        source_artifact_id="art-1",
        title="Deploy payments-api",
        description="rolling update",
        entity_id=None,
        entity_name=None,
        root_tier="tier-1",
    )
    assert record.risk == "high"
    with Session(engine) as db:
        live = db.get(ChangeRecord, record.id)
        assert live.change_type == "deploy"
        assert live.status == "draft"


def test_blast_radius_transitive(client):
    from backend.routers.catalog import CatalogEntity, ServiceDependency
    from backend.services.change_service import transitive_dependents

    tenant = "default"
    ids = [f"svc-{os.getpid()}-{i}" for i in range(4)]
    with Session(engine) as db:
        entities = [
            CatalogEntity(
                id=ids[i],
                name=f"svc-{i}-{os.getpid()}",
                kind="Service",
                lifecycle="production",
                owner_team="team",
                tenant_id=tenant,
                tags=json.dumps(["tier-1"] if i == 0 else []),
            )
            for i in range(4)
        ]
        for e in entities:
            db.add(e)
        # ids[1] -> ids[0]  (svc1 calls svc0)
        # ids[2] -> ids[1]  (svc2 calls svc1)
        # ids[3] -> ids[2]  (svc3 calls svc2)
        for a, b in [(1, 0), (2, 1), (3, 2)]:
            db.add(
                ServiceDependency(
                    from_entity_id=ids[a],
                    to_entity_id=ids[b],
                    dep_type="calls",
                )
            )
        db.commit()

        radius = transitive_dependents(db, tenant, ids[0])
    ids_returned = {r["id"] for r in radius}
    assert ids[1] in ids_returned and ids[2] in ids_returned and ids[3] in ids_returned


@pytest.mark.asyncio
async def test_require_change_approval_gate_refuses_and_leaves_pending(client):
    from backend.db.models.access import ChangeRecord
    from backend.db.repositories.settings import update_settings
    from backend.services.change_service import mark_change_approved

    update_settings({"REQUIRE_CHANGE_APPROVAL": "true"})
    try:
        nonce = f"gate-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
        # Terraform-apply proposal without any ChangeRecord
        proposal = propose_artifact(
            tenant_id="default",
            username="admin",
            agent="infra_agent",
            connector="terraform",
            method="apply_plan",
            params={
                "plan_b64": "AAA=",
                "workspace": "dev",
                "working_directory": "/tmp/tf-gate",
                "destroy_count": 0,
                "nonce": nonce,
            },
            preview={"type": "terraform_plan", "workspace": "dev", "destroy_count": 0},
            grounding="live",
            summary="tf",
        )
        with Session(engine) as session:
            admin = _admin(session)

        with pytest.raises(HTTPException) as ei:
            await fulfill_artifact_approval(
                approval_id=proposal["id"],
                tenant_id="default",
                decided_by="admin",
                user=admin,
            )
        assert ei.value.status_code == 409
        assert "change" in str(ei.value.detail).lower()
        with Session(engine) as db:
            row = db.get(ArtifactApproval, proposal["id"])
            assert row.status == "pending"
            assert "admin" not in json.loads(row.approvers_json or "[]")

        # Now create+approve a ChangeRecord and retry — should succeed
        with Session(engine) as db:
            rec = ChangeRecord(
                tenant_id="default",
                change_type="terraform_apply",
                source_artifact_id=proposal["id"],
                title="Deploy tf",
                description="",
                status="approved",
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)

        async def _fake_apply(**kwargs):
            return {"ok": True, "output": "applied"}

        with patch(
            "backend.services.terraform_service.apply_stored_plan",
            new=_fake_apply,
        ):
            out = await fulfill_artifact_approval(
                approval_id=proposal["id"],
                tenant_id="default",
                decided_by="admin",
                user=admin,
            )
        assert out.get("ok")
    finally:
        update_settings({"REQUIRE_CHANGE_APPROVAL": "false"})


@pytest.mark.asyncio
async def test_require_change_approval_off_allows_execution(client):
    from backend.db.repositories.settings import update_settings

    update_settings({"REQUIRE_CHANGE_APPROVAL": "false"})
    nonce = f"nogate-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="infra_agent",
        connector="terraform",
        method="apply_plan",
        params={
            "plan_b64": "AAA=",
            "workspace": "dev",
            "working_directory": "/tmp/tf-nogate",
            "destroy_count": 0,
            "nonce": nonce,
        },
        preview={"type": "terraform_plan", "workspace": "dev", "destroy_count": 0},
        grounding="live",
        summary="tf",
    )
    with Session(engine) as session:
        admin = _admin(session)

    async def _fake_apply(**kwargs):
        return {"ok": True, "output": "applied"}

    with patch(
        "backend.services.terraform_service.apply_stored_plan",
        new=_fake_apply,
    ):
        out = await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
    assert out.get("ok")


def test_close_change_links_recent_incident(client):
    from backend.db.models.access import ChangeRecord
    from backend.db.models.ops import Incident
    from backend.services.change_service import close_change_request

    tenant = f"close-{os.getpid()}"
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        rec = ChangeRecord(
            tenant_id=tenant,
            change_type="deploy",
            title="deploy x",
            description="",
            status="submitted",
            implemented_at=now,
        )
        db.add(rec)
        incident = Incident(
            timestamp=now + timedelta(minutes=30),
            severity="High",
            summary="post-deploy 5xx",
            root_cause="",
            raw_logs="",
            model_used="",
            raw_response="",
            tenant_id=tenant,
        )
        db.add(incident)
        db.commit()
        db.refresh(rec)
        db.refresh(incident)

    result = close_change_request(
        change_id=rec.id,
        tenant_id=tenant,
        outcome="success",
        actor="admin",
        implemented_at=now,
    )
    assert result["ok"]
    assert result["incident_id"] == incident.id


# ── Compliance agent ──────────────────────────────────────────────────────────


def test_collect_evidence_covers_six_controls(client):
    from backend.services.compliance_service import CONTROLS, collect_all_controls

    now = datetime.now(timezone.utc)
    result = collect_all_controls(
        tenant_id="default",
        period_start=now - timedelta(days=30),
        period_end=now,
    )
    assert set(result.keys()) == set(CONTROLS.keys())
    for cid, res in result.items():
        assert "evidence" in res
        assert "gaps" in res


def test_cc6_1_flags_admin_without_mfa(client):
    from backend.services.compliance_service import collect_evidence

    tenant = f"cc6-{os.getpid()}"
    with Session(engine) as db:
        db.add(
            User(
                username=f"badadmin-{os.getpid()}",
                email="badadmin@example.com",
                hashed_password=hash_password("Admin123!"),
                role="Admin",
                tenant_id=tenant,
                mfa_enabled=False,
            )
        )
        db.commit()
    now = datetime.now(timezone.utc)
    res = collect_evidence(
        control_id="SOC2-CC6.1",
        tenant_id=tenant,
        period_start=now - timedelta(days=1),
        period_end=now,
    )
    gap_types = {g["type"] for g in res.get("gaps") or []}
    assert "admin_without_mfa" in gap_types


def test_cc8_1_flags_change_without_record(client):
    from backend.services.compliance_service import collect_evidence

    tenant = f"cc8-{os.getpid()}"
    now = datetime.now(timezone.utc)
    with Session(engine) as db:
        approval = ArtifactApproval(
            tenant_id=tenant,
            username="admin",
            agent="infra_agent",
            connector="terraform",
            method="apply_plan",
            params_json="{}",
            preview_json="{}",
            idempotency_key=f"cc8-{os.getpid()}",
            status="approved",
            created_at=now,
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)
    res = collect_evidence(
        control_id="SOC2-CC8.1",
        tenant_id=tenant,
        period_start=now - timedelta(days=1),
        period_end=now + timedelta(hours=1),
    )
    gap_types = {g["type"] for g in res.get("gaps") or []}
    assert "change_without_record" in gap_types


def test_cc7_4_flags_high_severity_no_postmortem(client):
    from backend.db.models.ops import Incident
    from backend.services.compliance_service import collect_evidence

    tenant = f"cc74-{os.getpid()}"
    old = datetime.now(timezone.utc) - timedelta(days=10)
    with Session(engine) as db:
        inc = Incident(
            timestamp=old,
            severity="Critical",
            summary="broken",
            root_cause="",
            raw_logs="",
            model_used="",
            raw_response="",
            tenant_id=tenant,
            status="RESOLVED",
        )
        db.add(inc)
        db.commit()
    res = collect_evidence(
        control_id="SOC2-CC7.4",
        tenant_id=tenant,
        period_start=old - timedelta(days=1),
        period_end=datetime.now(timezone.utc),
    )
    gap_types = {g["type"] for g in res.get("gaps") or []}
    assert "high_severity_no_postmortem" in gap_types


@pytest.mark.asyncio
async def test_evidence_pack_is_hitl_gated_and_deferred(client):
    from backend.agents.compliance_agent import compliance_agent

    with Session(engine) as db:
        result = await compliance_agent.run(
            {"action": "generate_evidence_pack", "days": 7},
            _ctx(),
            db,
        )
    assert result.status == "pending_approval"
    # Before approval, no ZIP bytes are emitted in the result — only preview
    preview = result.details.get("preview") or {}
    assert "content_base64" not in preview

    # And the underlying artifact approval is pending
    approval_id = result.details.get("artifact_approval_id")
    assert approval_id
    with Session(engine) as db:
        row = db.get(ArtifactApproval, approval_id)
        assert row is not None
        assert row.status == "pending"

    # Approve — bytes are generated
    with Session(engine) as session:
        admin = _admin(session)
    out = await fulfill_artifact_approval(
        approval_id=row.id,
        tenant_id="default",
        decided_by="admin",
        user=admin,
    )
    assert out.get("ok")
    body = out.get("result") or {}
    assert body.get("content_type") == "application/zip"
    assert body.get("size_bytes", 0) > 0
    # Confirm ZIP contents include per-control files
    import base64 as _b64

    raw = _b64.b64decode(body["content_base64"])
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        assert "summary.json" in names
        assert any(n.startswith("SOC2-") for n in names)


# ── Onboarding / Offboarding ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_onboard_creates_step_per_resource(client):
    from backend.agents.onboarding_agent import onboarding_agent
    from backend.db.models.access import ResourceOwner, TeamAccessTemplate
    from backend.db.models.workflows import WorkflowDefinition

    tenant = "default"
    team = f"team-{os.getpid()}"
    with Session(engine) as db:
        template = TeamAccessTemplate(
            tenant_id=tenant,
            team_name=team,
            role_level="junior",
            resources_json=json.dumps(
                [
                    {"resource_type": "okta_group", "resource_id": "eng", "justification": "team"},
                    {"resource_type": "github_team", "resource_id": "payments", "justification": "team"},
                    {"resource_type": "jira_project", "resource_id": "PAY", "justification": "team"},
                ]
            ),
        )
        db.add(template)
        db.add(
            ResourceOwner(
                tenant_id=tenant,
                resource_type="okta_group",
                resource_id="eng",
                owner_username="alice",
            )
        )
        db.add(
            ResourceOwner(
                tenant_id=tenant,
                resource_type="github_team",
                resource_id="payments",
                owner_username="carol",
            )
        )
        db.commit()

    with Session(engine) as db:
        # bypass okta grounding for this test
        with patch.object(
            onboarding_agent, "_ground_okta", AsyncMock(return_value=MagicMock())
        ):
            result = await onboarding_agent.run(
                {
                    "action": "onboard",
                    "subject_username": "bob",
                    "team": team,
                    "role_level": "junior",
                },
                _ctx(),
                db,
            )
    assert result.status == "pending_approval"
    steps = result.details["steps"]
    hitl_steps = [s for s in steps if s["type"] == "hitl"]
    assert len(hitl_steps) == 3
    owners = {s.get("resource_id"): s.get("owner_username") for s in hitl_steps}
    assert owners["eng"] == "alice"
    assert owners["payments"] == "carol"
    # Unowned resource → admin fallback
    assert owners["PAY"] == "admin"

    with Session(engine) as db:
        wf = db.get(WorkflowDefinition, result.details["workflow_id"])
        assert wf is not None
        assert wf.name == "onboard:bob"


@pytest.mark.asyncio
async def test_offboard_lists_grants_and_puts_okta_last(client):
    from backend.agents.onboarding_agent import onboarding_agent
    from backend.db.models.access import AccessRequestRecord

    subject = f"leaver-{os.getpid()}"
    with Session(engine) as db:
        for i, rtype in enumerate(["okta_group", "github_team", "jira_project"]):
            db.add(
                AccessRequestRecord(
                    tenant_id="default",
                    requester_username=subject,
                    subject_username=subject,
                    resource_type=rtype,
                    resource_id=f"{rtype}-{i}",
                    resource_name=f"{rtype}-{i}",
                    owner_username="alice",
                    status="provisioned",
                    connector=rtype.split("_")[0],
                    connector_method="add_user_to_group",
                    connector_params_json="{}",
                )
            )
        db.commit()

    with Session(engine) as db:
        result = await onboarding_agent.run(
            {"action": "offboard", "subject_username": subject},
            _ctx(),
            db,
        )
    assert result.status == "pending_approval"
    steps = result.details["steps"]
    revocations = result.details["revocations"]
    assert len(revocations) == 3

    # Okta deactivate must be last, must be a connector step, and its gate must
    # depend on all revoke steps.
    okta_gate = next(s for s in steps if s["id"] == "okta_deactivate_gate")
    okta_deact = next(s for s in steps if s["id"] == "okta_deactivate")
    assert okta_gate["requires_separate_approval"] is True
    assert okta_deact["connector"] == "okta"
    assert okta_deact["method"] == "deactivate_user"
    assert okta_deact["depends_on"] == ["okta_deactivate_gate"]
    revoke_ids = [s["id"] for s in steps if s["id"].startswith("revoke_") and not s["id"].startswith("revoke_gate")]
    assert set(revoke_ids).issubset(set(okta_gate["depends_on"]))
    assert result.details["irreversible_final_step"] == "okta_deactivate"


@pytest.mark.asyncio
async def test_check_onboarding_status_reports_per_system(client):
    from backend.agents.onboarding_agent import onboarding_agent
    from backend.db.models.access import ResourceOwner, TeamAccessTemplate

    tenant = "default"
    team = f"team-status-{os.getpid()}"
    with Session(engine) as db:
        db.add(
            TeamAccessTemplate(
                tenant_id=tenant,
                team_name=team,
                role_level="junior",
                resources_json=json.dumps(
                    [{"resource_type": "okta_group", "resource_id": "eng-status"}]
                ),
            )
        )
        db.add(
            ResourceOwner(
                tenant_id=tenant,
                resource_type="okta_group",
                resource_id="eng-status",
                owner_username="alice",
            )
        )
        db.commit()

    with Session(engine) as db:
        with patch.object(
            onboarding_agent, "_ground_okta", AsyncMock(return_value=MagicMock())
        ):
            onboard = await onboarding_agent.run(
                {
                    "action": "onboard",
                    "subject_username": "bob-status",
                    "team": team,
                    "role_level": "junior",
                },
                _ctx(),
                db,
            )
    wf_id = onboard.details["workflow_id"]

    with Session(engine) as db:
        status = await onboarding_agent.run(
            {"action": "check_onboarding_status", "workflow_id": wf_id},
            _ctx(),
            db,
        )
    assert status.status == "success"
    per_system = status.details["per_system"]
    hitl_rows = [r for r in per_system if r["type"] == "hitl"]
    assert any(r["resource_id"] == "eng-status" for r in hitl_rows)
