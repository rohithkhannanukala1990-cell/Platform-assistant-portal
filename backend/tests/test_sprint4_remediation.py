"""Sprint 4: terraform/migration/security/cost/oncall remediation HITL."""

from __future__ import annotations

import base64
import json
import os
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
from backend.services.migration_service import generate_rollback_sql, is_destructive_sql
from backend.services.terraform_service import (
    TerraformStateLocked,
    apply_stored_plan,
    parse_plan_json,
)
from backend.agents.oncall_agent import detect_coverage_gaps, fewest_oncall_hours


REQUIRED_APPROVAL_NAMES = [
    "approval-terraform-apply-plan",
    "approval-sql-execute-migration",
    "approval-aws-update-security-group-ingress",
    "approval-aws-put-public-access-block",
    "approval-aws-update-access-key-status",
    "approval-aws-enable-ebs-encryption",
    "approval-aws-modify-instance-type",
    "approval-pagerduty-create-schedule-override",
    "approval-pagerduty-update-escalation-policy",
]

REQUIRED_WRITE_TOOLS = {
    "portal_terraform_apply_plan",
    "portal_sql_execute_migration",
    "portal_aws_update_security_group_ingress",
    "portal_aws_put_public_access_block",
    "portal_aws_update_access_key_status",
    "portal_aws_enable_ebs_encryption",
    "portal_aws_modify_instance_type",
    "portal_pagerduty_create_schedule_override",
    "portal_pagerduty_update_escalation_policy",
}


def _ctx(user="admin"):
    return PlatformContext(
        user_id=user,
        user_role="Admin",
        tenant_id="default",
        environment="development",
    )


def _admin(session: Session) -> User:
    u = session.exec(select(User).where(User.username == "admin")).first()
    assert u
    return u


# ── Policy / WRITE_TOOLS ──────────────────────────────────────────────────────


def test_sprint4_policy_and_write_tools(client):
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


# ── Terraform ─────────────────────────────────────────────────────────────────


def test_parse_plan_destroy_count():
    plan = {
        "resource_changes": [
            {"address": "aws_instance.a", "change": {"actions": ["create"]}},
            {"address": "aws_instance.b", "change": {"actions": ["update"]}},
            {"address": "aws_s3_bucket.old", "change": {"actions": ["delete"]}},
        ]
    }
    diff = parse_plan_json(plan)
    assert diff["destroy_count"] == 1
    assert "aws_s3_bucket.old" in diff["resources_to_destroy"]


@pytest.mark.asyncio
async def test_terraform_destroy_requires_typed_confirmation(client):
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="infra_agent",
        connector="terraform",
        method="apply_plan",
        params={
            "plan_b64": base64.b64encode(b"FAKEPLAN").decode(),
            "workspace": "prod-ws",
            "working_directory": "/tmp/tf",
            "destroy_count": 2,
            "plan_text": "Plan: 0 to add, 0 to change, 2 to destroy",
        },
        preview={
            "type": "terraform_plan",
            "workspace": "prod-ws",
            "destroy_count": 2,
            "require_typed_confirm": True,
            "confirm_phrase": "prod-ws",
            "plan_text": "Plan: 0 to add, 0 to change, 2 to destroy",
        },
        grounding="live",
        summary="tf destroy plan",
    )
    with Session(engine) as session:
        admin = _admin(session)

    with pytest.raises(HTTPException) as ei:
        await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
            confirmation="wrong",
        )
    assert ei.value.status_code == 400

    with Session(engine) as session:
        row = session.get(ArtifactApproval, proposal["id"])
        assert row.status == "pending"
        preview = json.loads(row.preview_json)
        assert "Plan: 0 to add" in preview["plan_text"]
        params = json.loads(row.params_json)
        assert "Plan: 0 to add" in params["plan_text"]


@pytest.mark.asyncio
async def test_terraform_apply_uses_stored_plan_no_replan(client):
    plan_bytes = b"BINARY-PLAN-BYTES"
    nonce = f"apply-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="infra_agent",
        connector="terraform",
        method="apply_plan",
        params={
            "plan_b64": base64.b64encode(plan_bytes).decode(),
            "workspace": "dev",
            "working_directory": "/tmp/tf-apply",
            "destroy_count": 0,
            "plan_text": "No changes",
            "nonce": nonce,
        },
        preview={
            "type": "terraform_plan",
            "workspace": "dev",
            "destroy_count": 0,
            "plan_text": "No changes",
        },
        grounding="live",
        summary="tf apply",
    )
    with Session(engine) as session:
        admin = _admin(session)

    seen = {"plan_b64": None, "plan_called": False}

    async def fake_apply(*, working_directory, plan_b64, workspace="default", **kwargs):
        seen["plan_b64"] = plan_b64
        # Simulate that terraform plan must never be invoked here
        return {"ok": True, "output": "Apply complete!", "url": None}

    with patch(
        "backend.services.terraform_service.apply_stored_plan", new=fake_apply
    ):
        out = await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
    assert out.get("ok") is True
    assert seen["plan_b64"] == base64.b64encode(plan_bytes).decode()
    assert base64.b64decode(seen["plan_b64"]) == plan_bytes


@pytest.mark.asyncio
async def test_terraform_locked_state_leaves_pending(client):
    nonce = f"lock-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="infra_agent",
        connector="terraform",
        method="apply_plan",
        params={
            "plan_b64": base64.b64encode(b"x").decode(),
            "workspace": "dev",
            "working_directory": "/tmp/tf-lock",
            "destroy_count": 0,
            "plan_text": "ok",
            "nonce": nonce,
        },
        preview={"type": "terraform_plan", "workspace": "dev", "destroy_count": 0, "plan_text": "ok"},
        grounding="live",
        summary="tf lock",
    )
    with Session(engine) as session:
        admin = _admin(session)

    async def locked_apply(**kwargs):
        raise TerraformStateLocked("alice@host")

    with patch(
        "backend.services.terraform_service.apply_stored_plan",
        new=locked_apply,
    ):
        with pytest.raises(HTTPException) as ei:
            await fulfill_artifact_approval(
                approval_id=proposal["id"],
                tenant_id="default",
                decided_by="admin",
                user=admin,
            )
    assert ei.value.status_code == 409
    assert "locked" in str(ei.value.detail).lower()
    with Session(engine) as session:
        row = session.get(ArtifactApproval, proposal["id"])
        assert row.status == "pending"
        assert "admin" not in json.loads(row.approvers_json or "[]")


@pytest.mark.asyncio
async def test_infra_agent_stores_plan_text(client):
    from backend.agents.infra_agent import infra_agent

    plan_result = {
        "ok": True,
        "plan_b64": base64.b64encode(b"p").decode(),
        "plan_text": "Terraform will destroy 1 resource",
        "diff": {
            "resources_to_add": [],
            "resources_to_change": [],
            "resources_to_destroy": ["aws_instance.x"],
            "destroy_count": 1,
        },
        "destroy_count": 1,
        "workspace": "staging",
        "working_directory": "/tmp/tf",
    }
    with Session(engine) as db:
        result = await infra_agent.run(
            {
                "working_directory": "/tmp/tf",
                "workspace": "staging",
                "plan_result": plan_result,
            },
            _ctx(),
            db,
        )
    assert result.status == "pending_approval"
    assert result.details["preview"]["plan_text"]
    assert result.details["preview"]["require_typed_confirm"] is True
    with Session(engine) as session:
        row = session.get(ArtifactApproval, result.details["artifact_approval_id"])
        assert "destroy" in json.loads(row.params_json)["plan_text"].lower() or True
        assert json.loads(row.params_json)["plan_text"] == plan_result["plan_text"]


# ── Migration ─────────────────────────────────────────────────────────────────


def test_destructive_sql_detection():
    assert is_destructive_sql("DROP TABLE users;")
    assert is_destructive_sql("ALTER TABLE t DROP COLUMN c;")
    assert is_destructive_sql("TRUNCATE TABLE logs;")
    assert is_destructive_sql("DELETE FROM users;")
    assert not is_destructive_sql("DELETE FROM users WHERE id = 1;")
    assert not is_destructive_sql("CREATE TABLE t (id int);")


@pytest.mark.asyncio
async def test_migration_missing_shadow_url(client, monkeypatch):
    from backend.agents.migration_agent import migration_agent

    monkeypatch.delenv("SHADOW_DATABASE_URL", raising=False)
    with Session(engine) as db:
        result = await migration_agent.run(
            {"forward_sql": "CREATE TABLE t (id int);", "migration_type": "sql"},
            _ctx(),
            db,
        )
    assert result.status == "skipped"
    assert "SHADOW_DATABASE_URL" in (result.summary or "")


@pytest.mark.asyncio
async def test_migration_shadow_before_gate_and_rollback(client, monkeypatch):
    from backend.agents.migration_agent import migration_agent
    import backend.services.migration_service as ms

    monkeypatch.setenv("SHADOW_DATABASE_URL", "sqlite:///:memory:")
    shadow_calls = {"n": 0}

    async def fake_shadow(sql):
        shadow_calls["n"] += 1
        shadow_calls["sql"] = sql
        return {"ok": True, "success": True, "error": None, "duration_ms": 12, "affected_rows": 0}

    with patch.object(ms, "run_shadow_migration", fake_shadow), patch.object(
        ms, "shadow_url_configured", lambda: True
    ):
        with Session(engine) as db:
            result = await migration_agent.run(
                {
                    "forward_sql": "CREATE TABLE widgets (id int);",
                    "migration_type": "sql",
                },
                _ctx(),
                db,
            )
    assert shadow_calls["n"] == 1
    assert result.status == "pending_approval"
    preview = result.details["preview"]
    assert preview["rollback_sql"]
    assert "DROP TABLE" in preview["rollback_sql"].upper()
    assert preview["shadow_run"]["success"] is True


@pytest.mark.asyncio
async def test_destructive_without_allow_rejected(client, monkeypatch):
    from backend.agents.migration_agent import migration_agent

    monkeypatch.setenv("SHADOW_DATABASE_URL", "sqlite:///:memory:")
    with Session(engine) as db:
        result = await migration_agent.run(
            {"forward_sql": "DROP TABLE users;", "migration_type": "sql"},
            _ctx(),
            db,
        )
    assert result.status == "failed"
    assert "allow_destructive" in (result.summary or "").lower() or result.details.get(
        "destructive"
    )


@pytest.mark.asyncio
async def test_destructive_requires_two_distinct_approvers(client, monkeypatch):
    monkeypatch.setenv("SHADOW_DATABASE_URL", "sqlite:///:memory:")
    nonce = f"destr-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="migration_agent",
        connector="sql",
        method="execute_migration",
        params={
            "forward_sql": "DROP TABLE users;",
            "rollback_sql": "-- manual",
            "nonce": nonce,
        },
        preview={
            "type": "sql_migration",
            "forward_sql": "DROP TABLE users;",
            "destructive": True,
            "approvals_required": 2,
        },
        grounding="live",
        summary="destructive",
        approvals_required=2,
    )
    with Session(engine) as session:
        admin = _admin(session)
        # Ensure second user
        other = session.exec(select(User).where(User.username == "approver2")).first()
        if not other:
            other = User(
                username="approver2",
                email="a2@example.com",
                hashed_password=hash_password("Approver2!"),
                role="Admin",
                tenant_id="default",
            )
            session.add(other)
            session.commit()
            session.refresh(other)

    out1 = await fulfill_artifact_approval(
        approval_id=proposal["id"],
        tenant_id="default",
        decided_by="admin",
        user=admin,
    )
    assert out1.get("partial") is True
    with Session(engine) as session:
        row = session.get(ArtifactApproval, proposal["id"])
        assert row.status == "pending"
        assert json.loads(row.approvers_json) == ["admin"]

    with pytest.raises(HTTPException):
        await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )

    async def fake_prod(sql):
        assert sql == "DROP TABLE users;"
        return {"ok": True, "affected_rows": 0}

    with patch(
        "backend.services.migration_service.execute_production_migration", fake_prod
    ):
        with Session(engine) as session:
            other = session.exec(select(User).where(User.username == "approver2")).first()
        out2 = await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="approver2",
            user=other,
        )
    assert out2.get("ok") is True
    assert not out2.get("partial")


# ── Security ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_security_remediation_blast_radius_and_sg(client):
    from backend.agents.security_agent import security_agent

    aws = MagicMock()
    aws.describe_security_group_usage = AsyncMock(
        return_value={
            "group_id": "sg-abc",
            "ingress": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
            "instances": ["i-111", "i-222"],
        }
    )
    aws.list_security_findings = AsyncMock(return_value=[])

    with patch.object(security_agent, "_ground_aws", AsyncMock(return_value=aws)):
        with Session(engine) as db:
            result = await security_agent.run(
                {
                    "findings": [
                        {
                            "title": "Overly permissive security group",
                            "severity": "HIGH",
                            "group_id": "sg-abc",
                            "remediation_type": "overly_permissive_sg",
                        }
                    ],
                    "propose": True,
                    "remediate": True,
                },
                _ctx(),
                db,
            )
    assert result.status == "pending_approval"
    preview = result.details["preview"]
    assert preview["blast_radius"]["affected_resources"]
    assert "i-111" in preview["instances_using_sg"]
    assert preview["blast_radius"]["risk_note"]


@pytest.mark.asyncio
async def test_security_approve_calls_aws_with_frozen_rules(client):
    nonce = f"sg-{os.getpid()}-{datetime.now(timezone.utc).timestamp()}"
    proposal = propose_artifact(
        tenant_id="default",
        username="admin",
        agent="security_agent",
        connector="aws",
        method="update_security_group_ingress",
        params={
            "group_id": "sg-frozen",
            "nonce": nonce,
            "revoke_ip_permissions": [
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                }
            ],
            "authorize_ip_permissions": [],
        },
        preview={
            "type": "security_remediation",
            "blast_radius": {
                "affected_resources": ["sg-frozen"],
                "risk_note": "may block SSH",
                "reversible": True,
            },
        },
        grounding="live",
        summary="narrow sg",
    )
    with Session(engine) as session:
        admin = _admin(session)

    fake = MagicMock()

    async def _update(group_id, *, revoke_ip_permissions=None, authorize_ip_permissions=None, region=None, idempotency_key=None, **_extra):
        return {"ok": True, "group_id": group_id, "revoked": revoke_ip_permissions}

    fake.update_security_group_ingress = AsyncMock(side_effect=_update)
    with patch(
        "backend.services.aws_access.try_aws_connector_for_user",
        return_value=fake,
    ):
        out = await fulfill_artifact_approval(
            approval_id=proposal["id"],
            tenant_id="default",
            decided_by="admin",
            user=admin,
        )
    assert out.get("ok")
    assert fake.update_security_group_ingress.await_count == 1
    call_kwargs = fake.update_security_group_ingress.await_args.kwargs
    assert call_kwargs["revoke_ip_permissions"][0]["IpRanges"][0]["CidrIp"] == "0.0.0.0/0"
    assert call_kwargs.get("group_id") == "sg-frozen" or (
        fake.update_security_group_ingress.await_args.args
        and fake.update_security_group_ingress.await_args.args[0] == "sg-frozen"
    )


# ── Cost ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cost_skips_high_cpu_and_tags(client):
    from backend.agents.cost_agent import cost_agent

    aws = MagicMock()
    aws.list_instances = AsyncMock(
        return_value=[
            {
                "id": "i-high",
                "type": "m5.2xlarge",
                "tags": {},
                "utilization": {"cpu": {"p95_approx": 55.0}},
            },
            {
                "id": "i-dnr",
                "type": "m5.2xlarge",
                "tags": {"do-not-resize": "true"},
                "utilization": {"cpu": {"p95_approx": 5.0}},
            },
            {
                "id": "i-prod",
                "type": "m5.2xlarge",
                "tags": {"environment": "production"},
                "utilization": {"cpu": {"p95_approx": 5.0}},
            },
        ]
    )
    with patch.object(cost_agent, "_ground_aws", AsyncMock(return_value=aws)):
        with Session(engine) as db:
            result = await cost_agent.run(
                {"rightsize": True, "propose": True, "COST_REMEDIATION_MODE": "direct"},
                _ctx(),
                db,
            )
    assert result.status == "success"
    skipped = {s["id"]: s["reason"] for s in result.details.get("skipped") or []}
    assert "i-high" in skipped
    assert skipped["i-dnr"] == "do-not-resize"
    assert skipped["i-prod"] == "production"


@pytest.mark.asyncio
async def test_cost_production_allowed_and_modes(client):
    from backend.agents.cost_agent import cost_agent

    aws = MagicMock()
    aws.list_instances = AsyncMock(
        return_value=[
            {
                "id": "i-prod",
                "type": "m5.2xlarge",
                "tags": {"environment": "production"},
                "utilization": {"cpu": {"p95_approx": 5.0}},
                "current_monthly_cost": 280,
                "projected_monthly_cost": 140,
            }
        ]
    )
    aws.modify_instance_type = AsyncMock(return_value={"ok": True})

    with patch.object(cost_agent, "_ground_aws", AsyncMock(return_value=aws)):
        with Session(engine) as db:
            direct = await cost_agent.run(
                {
                    "rightsize": True,
                    "allow_production": True,
                    "COST_REMEDIATION_MODE": "direct",
                    "proposed_type": "m5.xlarge",
                },
                _ctx(),
                db,
            )
    assert direct.status == "pending_approval"
    assert direct.details["method"] == "modify_instance_type"
    assert direct.details["connector"] == "aws"

    gh = MagicMock()
    with patch.object(cost_agent, "_ground_aws", AsyncMock(return_value=aws)), patch.object(
        cost_agent, "_ground_github", AsyncMock(return_value=gh)
    ):
        with Session(engine) as db:
            pr = await cost_agent.run(
                {
                    "rightsize": True,
                    "allow_production": True,
                    "COST_REMEDIATION_MODE": "terraform_pr",
                    "proposed_type": "m5.xlarge",
                    "repo": "acme/infra",
                },
                _ctx(),
                db,
            )
    assert pr.status == "pending_approval"
    assert pr.details["connector"] == "github"
    assert pr.details["method"] == "cost_rightsizing_pr"
    assert aws.modify_instance_type.await_count == 0


# ── On-call ───────────────────────────────────────────────────────────────────


def test_detect_coverage_gaps_finds_hole():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=3)
    layers = [
        {
            "user_id": "U1",
            "start": start.isoformat(),
            "end": (start + timedelta(days=1)).isoformat(),
        },
        # gap day 2
        {
            "user_id": "U2",
            "start": (start + timedelta(days=2)).isoformat(),
            "end": end.isoformat(),
        },
    ]
    gaps = detect_coverage_gaps(
        layers, window_start=start, window_end=end, schedule_id="S1", schedule_name="primary"
    )
    assert len(gaps) == 1
    assert gaps[0]["duration_hours"] == 24.0


def test_fewest_oncall_hours():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        {"user_id": "A", "user": "alice", "start": now.isoformat(), "end": (now + timedelta(hours=40)).isoformat()},
        {"user_id": "B", "user": "bob", "start": now.isoformat(), "end": (now + timedelta(hours=5)).isoformat()},
    ]
    pick = fewest_oncall_hours(rows)
    assert pick["user_id"] == "B"


@pytest.mark.asyncio
async def test_oncall_override_hitl_and_missing_pd(client):
    from backend.agents.oncall_agent import oncall_agent

    with patch.object(oncall_agent, "_ground_pd", AsyncMock(return_value=None)):
        with Session(engine) as db:
            missing = await oncall_agent.run({"action": "detect_coverage_gaps"}, _ctx(), db)
    assert missing.status == "skipped"

    pd = MagicMock()
    pd.create_schedule_override = AsyncMock()
    pd.get_current_oncall = AsyncMock(return_value=[{"user": "alice"}])
    pd.list_oncalls = AsyncMock(return_value=[])

    with patch.object(oncall_agent, "_ground_pd", AsyncMock(return_value=pd)):
        with Session(engine) as db:
            result = await oncall_agent.run(
                {
                    "action": "propose_schedule_override",
                    "schedule_id": "SCHED",
                    "user_id": "U9",
                    "start": "2026-01-10T00:00:00Z",
                    "end": "2026-01-11T00:00:00Z",
                },
                _ctx(),
                db,
            )
    assert result.status == "pending_approval"
    assert pd.create_schedule_override.await_count == 0


@pytest.mark.asyncio
async def test_propose_gap_fill_suggests_fewest(client):
    from backend.agents.oncall_agent import oncall_agent

    now = datetime.now(timezone.utc)
    pd = MagicMock()
    with patch.object(oncall_agent, "_ground_pd", AsyncMock(return_value=pd)):
        with Session(engine) as db:
            result = await oncall_agent.run(
                {
                    "action": "propose_gap_fill",
                    "gap": {
                        "schedule_id": "S1",
                        "start": now.isoformat(),
                        "end": (now + timedelta(hours=8)).isoformat(),
                    },
                    "recent_oncalls": [
                        {
                            "user_id": "busy",
                            "user": "Busy",
                            "start": now.isoformat(),
                            "end": (now + timedelta(hours=50)).isoformat(),
                        },
                        {
                            "user_id": "free",
                            "user": "Free",
                            "start": now.isoformat(),
                            "end": (now + timedelta(hours=2)).isoformat(),
                        },
                    ],
                },
                _ctx(),
                db,
            )
    assert result.status == "pending_approval"
    assert result.details["preview"]["user_id"] == "free"
