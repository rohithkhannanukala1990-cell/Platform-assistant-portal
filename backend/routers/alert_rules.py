"""Alert correlation rules admin API (Phase G4 — rules-based, not ML)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..auth import User, get_current_user, require_admin, write_audit
from ..database import engine
from ..db.models.alerts import VALID_ALERT_ACTIONS, AlertRule
from ..services.alert_rules import _serialize_rule, evaluate_alert_dry_run, list_alert_rules
from ..services.isolation import require_tenant
from ..observability.metrics import alert_correlation_counters

router = APIRouter(prefix="/api/alert-rules", tags=["alert-rules"])


class AlertRuleBody(BaseModel):
    name: str
    match_service: Optional[str] = None
    match_severity: Optional[str] = None
    match_title_regex: Optional[str] = None
    group_window_sec: int = 300
    action: str = "create_incident"
    priority: int = 100
    enabled: bool = True


class AlertDryRunBody(BaseModel):
    title: Optional[str] = None
    service: Optional[str] = None
    severity: Optional[str] = None
    source: str = "dry-run"
    log_text: str = ""
    payload: Optional[dict] = None


@router.get("/stats")
def alert_rule_stats(request: Request, current_user: User = Depends(require_admin)):
    """Admin counters for rules-based correlation (not ML)."""
    _ = require_tenant(request)
    return alert_correlation_counters()


@router.post("/dry-run")
def alert_rule_dry_run(
    request: Request,
    body: AlertDryRunBody,
    current_user: User = Depends(get_current_user),
):
    """Preview which rule would match — no bucket/metric side effects."""
    tenant_id = require_tenant(request)
    payload = dict(body.payload or {})
    if body.title:
        payload.setdefault("title", body.title)
    if body.service:
        payload.setdefault("service", body.service)
    if body.severity:
        payload.setdefault("severity", body.severity)
    return evaluate_alert_dry_run(
        tenant_id=tenant_id,
        source=body.source or "dry-run",
        log_text=body.log_text or body.title or "",
        payload=payload,
    )


def _validate_body(body: AlertRuleBody) -> None:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    if body.action not in VALID_ALERT_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"action must be one of {sorted(VALID_ALERT_ACTIONS)}",
        )
    if body.group_window_sec < 0:
        raise HTTPException(status_code=400, detail="group_window_sec must be >= 0")
    if body.match_title_regex:
        try:
            re.compile(body.match_title_regex)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"invalid match_title_regex: {exc}")


def _get_rule(session: Session, rule_id: str, tenant_id: str) -> AlertRule:
    rule = session.get(AlertRule, rule_id)
    if not rule or rule.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.get("")
def list_rules(request: Request, current_user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    return list_alert_rules(tenant_id)


@router.post("", status_code=201)
def create_rule(request: Request, body: AlertRuleBody, admin: User = Depends(require_admin)):
    _validate_body(body)
    tenant_id = require_tenant(request)
    now = datetime.now(timezone.utc)
    rule = AlertRule(
        name=body.name.strip(),
        tenant_id=tenant_id,
        match_service=(body.match_service or None),
        match_severity=(body.match_severity or None),
        match_title_regex=(body.match_title_regex or None),
        group_window_sec=body.group_window_sec,
        action=body.action,
        priority=body.priority,
        enabled=body.enabled,
        created_at=now,
        updated_at=now,
    )
    with Session(engine) as session:
        session.add(rule)
        session.commit()
        session.refresh(rule)
        out = _serialize_rule(rule)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="alert_rule_created",
        resource=f"alert_rule:{rule.id}",
        detail=rule.name,
    )
    return out


@router.put("/{rule_id}")
def update_rule(
    request: Request,
    rule_id: str,
    body: AlertRuleBody,
    admin: User = Depends(require_admin),
):
    _validate_body(body)
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        rule = _get_rule(session, rule_id, tenant_id)
        rule.name = body.name.strip()
        rule.match_service = body.match_service or None
        rule.match_severity = body.match_severity or None
        rule.match_title_regex = body.match_title_regex or None
        rule.group_window_sec = body.group_window_sec
        rule.action = body.action
        rule.priority = body.priority
        rule.enabled = body.enabled
        rule.updated_at = datetime.now(timezone.utc)
        session.add(rule)
        session.commit()
        session.refresh(rule)
        out = _serialize_rule(rule)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="alert_rule_updated",
        resource=f"alert_rule:{rule_id}",
        detail=body.name,
    )
    return out


@router.delete("/{rule_id}", status_code=204)
def delete_rule(request: Request, rule_id: str, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    with Session(engine) as session:
        rule = _get_rule(session, rule_id, tenant_id)
        session.delete(rule)
        session.commit()
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="alert_rule_deleted",
        resource=f"alert_rule:{rule_id}",
        detail="",
    )
