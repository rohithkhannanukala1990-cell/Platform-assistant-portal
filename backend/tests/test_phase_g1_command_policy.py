"""Phase G1 — Guardrails v2: structured command policy engine."""

from __future__ import annotations

import asyncio

from sqlmodel import Session, select

from backend.auth import User, engine, hash_password
from backend.command_validator import CommandValidator
from backend.context import PlatformContext
from backend.db.models.policy import CommandPolicyRule
from backend.executor.safe_executor import safe_executor
from backend.services.command_policy import evaluate_command, evaluate_commands
from backend.tests.conftest import auth_headers


def _make_user(username: str, *, tenant_id: str = "default", role: str = "User") -> User:
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            existing.tenant_id = tenant_id
            existing.role = role
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


def _login(client, username: str) -> str:
    r = client.post(
        "/auth/login",
        data={"username": username, "password": "Password123!"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _add_rule(**kwargs) -> CommandPolicyRule:
    import json as _json

    defaults = dict(
        name="test-rule",
        priority=5,
        enabled=True,
        match_roles='["*"]',
        match_environments='["*"]',
        match_tools='["*"]',
        match_command_prefixes="[]",
        match_regex=None,
        effect="deny",
        description="test",
        tenant_id=None,
    )
    for key in ("match_roles", "match_environments", "match_tools", "match_command_prefixes"):
        if key in kwargs and isinstance(kwargs[key], list):
            kwargs[key] = _json.dumps(kwargs[key])
    defaults.update(kwargs)
    row = CommandPolicyRule(**defaults)
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def _delete_rule(rule_id: str) -> None:
    with Session(engine) as session:
        row = session.get(CommandPolicyRule, rule_id)
        if row:
            session.delete(row)
            session.commit()


# ── 1. baseline blocklist still denies ───────────────────────────────────────

def test_baseline_still_blocks_rm_rf(client):
    decision = evaluate_command("rm -rf /", role="Admin", environment="development")
    assert decision.effect == "deny"
    assert "baseline_blocklist" in decision.matched_rule_ids
    assert not decision.safe_for_auto

    # Legacy context-free API is unchanged
    check = CommandValidator.validate(["rm -rf /"])
    assert not check.safe


# ── 2 + 3. production seeded rules ────────────────────────────────────────────

def test_production_kubectl_delete_requires_approval(client):
    decision = evaluate_command(
        "kubectl delete pod api-123", role="Admin", environment="production"
    )
    assert decision.effect == "require_approval"
    assert decision.matched_rule_ids, "a seeded rule should have matched"


def test_production_kubectl_get_allowed(client):
    decision = evaluate_command(
        "kubectl get pods -n web", role="User", environment="production"
    )
    assert decision.effect == "allow"
    assert decision.safe_for_auto


def test_production_catchall_requires_approval_for_unknown_command(client):
    decision = evaluate_command(
        "systemctl restart nginx", role="Admin", environment="production"
    )
    assert decision.effect == "require_approval"


def test_unparseable_command_fails_closed(client):
    decision = evaluate_command(
        'echo "unterminated', role="Admin", environment="development"
    )
    assert decision.effect == "require_approval"
    assert "parse_failure" in decision.matched_rule_ids


def test_worst_effect_wins_across_commands(client):
    decision = evaluate_commands(
        ["kubectl get pods", "rm -rf /"], role="Admin", environment="development"
    )
    assert decision.effect == "deny"


# ── 4. deny rule stops SafeExecutor ──────────────────────────────────────────

def test_deny_rule_stops_safe_executor(client):
    rule = _add_rule(
        name="g1-deny-systemctl-stop",
        effect="deny",
        match_command_prefixes=["systemctl stop"],
        priority=5,
    )
    try:
        out = asyncio.run(
            safe_executor.execute(
                ["systemctl stop nginx"],
                incident_id=0,
                approved_by="g1-test",
                context={
                    "role": "Admin",
                    "environment": "development",
                    "tool": "shell",
                    "approved": True,  # deny cannot be overridden by approval
                },
            )
        )
        assert out["success"] is False
        assert out.get("policy_effect") == "deny"
        assert out.get("blocked_at") == 0
    finally:
        _delete_rule(rule.id)


def test_approval_required_refused_without_flag(client):
    out = asyncio.run(
        safe_executor.execute(
            ["kubectl scale deployment api --replicas=3"],
            incident_id=0,
            approved_by="g1-test",
            context={
                "role": "Admin",
                "environment": "development",
                "tool": "kubernetes",
                "approved": False,
            },
        )
    )
    assert out["success"] is False
    assert out.get("policy_effect") == "require_approval"
    assert out.get("requires_approval") is True


# ── 5. orchestrator forces approval ──────────────────────────────────────────

def test_orchestrator_forces_approval_on_policy(client):
    from backend.agents.base import AgentResult
    from backend.pipeline.orchestrator import _validate_commands_in_result

    context = PlatformContext(
        user_id="g1-orch",
        user_role="Admin",
        environment="production",
        tenant_id="default",
    )
    result = AgentResult(
        agent="test_agent",
        status="success",
        summary="scale up",
        details={"commands": ["kubectl scale deployment api --replicas=5"]},
        timestamp="2026-01-01T00:00:00+00:00",
        triggered_by="g1-orch",
        workspace="ws-g1",
        environment="production",
    )
    validated = _validate_commands_in_result(result, context)
    assert validated.requires_approval is True
    assert validated.status != "failed"
    assert validated.details.get("policy_effect") == "require_approval"


def test_orchestrator_denies_bad_commands(client):
    from backend.agents.base import AgentResult
    from backend.pipeline.orchestrator import _validate_commands_in_result

    context = PlatformContext(
        user_id="g1-orch",
        user_role="Admin",
        environment="development",
        tenant_id="default",
    )
    result = AgentResult(
        agent="test_agent",
        status="pending_approval",
        summary="nuke",
        details={"commands": ["rm -rf /"]},
        requires_approval=True,
        approval_payload={"commands": ["rm -rf /"]},
        timestamp="2026-01-01T00:00:00+00:00",
        triggered_by="g1-orch",
        workspace="ws-g1",
        environment="development",
    )
    validated = _validate_commands_in_result(result, context)
    assert validated.status == "failed"
    assert validated.requires_approval is False
    assert validated.approval_payload in (None, {})


# ── 6. API authz ──────────────────────────────────────────────────────────────

def test_non_admin_cannot_modify_rules(client, admin_token):
    _make_user("g1-plain-user", role="User")
    user_token = _login(client, "g1-plain-user")

    listed = client.get("/api/policies/commands", headers=auth_headers(user_token))
    assert listed.status_code == 200
    rules = listed.json()
    assert rules, "seeded rules expected"
    target = rules[0]

    put = client.put(
        f"/api/policies/commands/{target['id']}",
        headers=auth_headers(user_token),
        json={"name": "hijack", "effect": "allow"},
    )
    assert put.status_code == 403

    post = client.post(
        "/api/policies/commands",
        headers=auth_headers(user_token),
        json={"name": "hijack", "effect": "allow"},
    )
    assert post.status_code == 403

    delete = client.delete(
        f"/api/policies/commands/{target['id']}", headers=auth_headers(user_token)
    )
    assert delete.status_code == 403


def test_admin_crud_and_evaluate_endpoint(client, admin_token):
    h = auth_headers(admin_token)
    created = client.post(
        "/api/policies/commands",
        headers=h,
        json={
            "name": "g1-api-rule",
            "priority": 7,
            "effect": "deny",
            "match_command_prefixes": ["shutdown"],
            "description": "no shutdowns",
        },
    )
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]

    try:
        ev = client.post(
            "/api/policies/commands/evaluate",
            headers=h,
            json={"command": "shutdown -h now", "environment": "development"},
        )
        assert ev.status_code == 200
        body = ev.json()
        assert body["effect"] == "deny"
        assert rule_id in body["matched_rule_ids"]

        updated = client.put(
            f"/api/policies/commands/{rule_id}",
            headers=h,
            json={
                "name": "g1-api-rule",
                "priority": 7,
                "effect": "require_approval",
                "match_command_prefixes": ["shutdown"],
            },
        )
        assert updated.status_code == 200
        assert updated.json()["effect"] == "require_approval"
    finally:
        deleted = client.delete(f"/api/policies/commands/{rule_id}", headers=h)
        assert deleted.status_code == 200


# ── 7. tenant isolation ───────────────────────────────────────────────────────

def test_tenant_scoped_rule_isolated(client):
    rule = _add_rule(
        name="g1-tenant-b-deny-echo",
        effect="deny",
        match_command_prefixes=["echo"],
        priority=5,
        tenant_id="tenant-b",
    )
    try:
        # tenant-b sees the deny
        b = evaluate_command("echo hello", role="User", environment="development", tenant_id="tenant-b")
        assert b.effect == "deny"

        # default tenant is unaffected
        a = evaluate_command("echo hello", role="User", environment="development", tenant_id="default")
        assert a.effect == "allow"

        # default-tenant user cannot see or edit tenant-b's rule via API
        _make_user("g1-admin-default", role="Admin", tenant_id="default")
        token = _login(client, "g1-admin-default")
        listed = client.get("/api/policies/commands", headers=auth_headers(token))
        assert rule.id not in [r["id"] for r in listed.json()]
        put = client.put(
            f"/api/policies/commands/{rule.id}",
            headers=auth_headers(token),
            json={"name": "steal", "effect": "allow"},
        )
        assert put.status_code == 404
    finally:
        _delete_rule(rule.id)
