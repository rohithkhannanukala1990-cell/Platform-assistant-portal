"""Command policy admin API — Guardrails v2 (Phase G1)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import User, get_current_user, require_admin, write_audit
from ..database import engine
from ..db.models.policy import VALID_EFFECTS, CommandPolicyRule
from ..services.command_policy import evaluate_command
from ..services.isolation import require_tenant

router = APIRouter(prefix="/api/policies/commands", tags=["command-policy"])


class RuleBody(BaseModel):
    name: str
    priority: int = 100
    enabled: bool = True
    match_roles: list[str] = ["*"]
    match_environments: list[str] = ["*"]
    match_tools: list[str] = ["*"]
    match_command_prefixes: list[str] = []
    match_regex: Optional[str] = None
    effect: str = "require_approval"
    max_risk: Optional[str] = None
    description: str = ""
    tenant_scoped: bool = False  # True → rule bound to caller's tenant


class EvaluateBody(BaseModel):
    command: str
    environment: str = "development"
    tool: str = "shell"


def _serialize(rule: CommandPolicyRule) -> dict:
    def _list(raw: str) -> list[str]:
        try:
            data = json.loads(raw or "[]")
            return [str(x) for x in data] if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    return {
        "id": rule.id,
        "name": rule.name,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "match_roles": _list(rule.match_roles),
        "match_environments": _list(rule.match_environments),
        "match_tools": _list(rule.match_tools),
        "match_command_prefixes": _list(rule.match_command_prefixes),
        "match_regex": rule.match_regex,
        "effect": rule.effect,
        "max_risk": rule.max_risk,
        "description": rule.description,
        "tenant_id": rule.tenant_id,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _validate_body(body: RuleBody) -> None:
    if body.effect not in VALID_EFFECTS:
        raise HTTPException(status_code=400, detail=f"effect must be one of {sorted(VALID_EFFECTS)}")
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.match_regex:
        try:
            re.compile(body.match_regex)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"invalid match_regex: {exc}")


def _get_visible_rule(session: Session, rule_id: str, tenant_id: str) -> CommandPolicyRule:
    rule = session.get(CommandPolicyRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if rule.tenant_id is not None and rule.tenant_id != tenant_id:
        # Tenant-scoped rule from another tenant: hide its existence.
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.get("")
def list_rules(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        rows = session.exec(select(CommandPolicyRule)).all()
    visible = [r for r in rows if r.tenant_id is None or r.tenant_id == tenant_id]
    visible.sort(key=lambda r: (r.priority, r.name))
    return [_serialize(r) for r in visible]


@router.post("", status_code=201)
def create_rule(request: Request, body: RuleBody, admin: User = Depends(require_admin)):
    _validate_body(body)
    tenant_id = require_tenant(request)
    rule = CommandPolicyRule(
        name=body.name.strip(),
        priority=body.priority,
        enabled=body.enabled,
        match_roles=json.dumps(body.match_roles),
        match_environments=json.dumps(body.match_environments),
        match_tools=json.dumps(body.match_tools),
        match_command_prefixes=json.dumps(body.match_command_prefixes),
        match_regex=(body.match_regex or None),
        effect=body.effect,
        max_risk=body.max_risk,
        description=body.description,
        tenant_id=tenant_id if body.tenant_scoped else None,
    )
    with Session(engine) as session:
        session.add(rule)
        session.commit()
        session.refresh(rule)
    write_audit(
        admin.username, admin.role, "command_policy_rule_created",
        resource=f"policy:{rule.id}", detail=f"{rule.name} → {rule.effect}",
    )
    return _serialize(rule)


@router.put("/{rule_id}")
def update_rule(
    request: Request, rule_id: str, body: RuleBody, admin: User = Depends(require_admin)
):
    _validate_body(body)
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        rule = _get_visible_rule(session, rule_id, tenant_id)
        rule.name = body.name.strip()
        rule.priority = body.priority
        rule.enabled = body.enabled
        rule.match_roles = json.dumps(body.match_roles)
        rule.match_environments = json.dumps(body.match_environments)
        rule.match_tools = json.dumps(body.match_tools)
        rule.match_command_prefixes = json.dumps(body.match_command_prefixes)
        rule.match_regex = body.match_regex or None
        rule.effect = body.effect
        rule.max_risk = body.max_risk
        rule.description = body.description
        rule.updated_at = datetime.now(timezone.utc)
        session.add(rule)
        session.commit()
        session.refresh(rule)
    write_audit(
        admin.username, admin.role, "command_policy_rule_updated",
        resource=f"policy:{rule.id}", detail=f"{rule.name} → {rule.effect}",
    )
    return _serialize(rule)


@router.delete("/{rule_id}")
def delete_rule(request: Request, rule_id: str, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        rule = _get_visible_rule(session, rule_id, tenant_id)
        name = rule.name
        session.delete(rule)
        session.commit()
    write_audit(
        admin.username, admin.role, "command_policy_rule_deleted",
        resource=f"policy:{rule_id}", detail=name,
    )
    return {"deleted": rule_id}


@router.post("/evaluate")
def evaluate(request: Request, body: EvaluateBody, current_user: User = Depends(get_current_user)):
    """Test a command against the policy engine (no execution)."""
    tenant_id = require_tenant(request)
    decision = evaluate_command(
        body.command,
        role=current_user.role,
        environment=body.environment,
        tool=body.tool,
        tenant_id=tenant_id,
    )
    return {"command": body.command, **decision.to_dict()}
