"""Rules-based alert correlation on ingest (Phase G4)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..db.core import engine
from ..db.models.alerts import (
    ACTION_ATTACH_EXISTING,
    ACTION_CREATE_INCIDENT,
    ACTION_SUPPRESS,
    VALID_ALERT_ACTIONS,
    AlertGroupBucket,
    AlertRule,
)
from ..observability.metrics import record_alert_grouped, record_alert_suppressed


@dataclass
class AlertFields:
    title: str
    service: str
    severity: str
    source: str
    log_text: str


@dataclass
class AlertIngestDecision:
    proceed: bool
    action: str
    rule_id: str | None = None
    rule_name: str | None = None
    incident_id: int | None = None
    reason: str = ""


def extract_alert_fields(
    payload: dict | None,
    *,
    source: str,
    log_text: str,
) -> AlertFields:
    """Normalize alert fields from common webhook payload shapes."""
    data = payload if isinstance(payload, dict) else {}
    title = (
        data.get("title")
        or data.get("message")
        or data.get("body")
        or data.get("summary")
        or data.get("alertname")
        or log_text
    )
    if isinstance(title, dict):
        title = title.get("summary") or json.dumps(title)
    title = str(title or "").strip()[:500]

    service = (
        data.get("service")
        or data.get("service_name")
        or (data.get("service", {}) or {}).get("summary")
        if isinstance(data.get("service"), dict)
        else data.get("service")
    )
    if not service and isinstance(data.get("labels"), dict):
        service = data["labels"].get("service") or data["labels"].get("job")
    if not service and isinstance(data.get("alerts"), list) and data["alerts"]:
        labels = (data["alerts"][0] or {}).get("labels") or {}
        service = labels.get("service") or labels.get("job")
    service = str(service or source or "unknown").strip()[:200]

    severity = (
        data.get("severity")
        or data.get("priority")
        or data.get("urgency")
        or data.get("status")
        or "unknown"
    )
    if isinstance(severity, dict):
        severity = severity.get("name") or severity.get("level") or "unknown"
    severity = str(severity).strip()[:50]

    return AlertFields(
        title=title,
        service=service,
        severity=severity,
        source=source,
        log_text=log_text,
    )


def _fingerprint(tenant_id: str, rule_id: str, fields: AlertFields) -> str:
    # Group by rule + service within the window (not exact title), so
    # matching alerts attach to the same incident during group_window_sec.
    raw = f"{tenant_id}|{rule_id}|{fields.service.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _rule_matches(rule: AlertRule, fields: AlertFields) -> bool:
    if not rule.enabled:
        return False
    if rule.match_service:
        needle = rule.match_service.strip().lower()
        if needle not in fields.service.lower():
            return False
    if rule.match_severity:
        if rule.match_severity.strip().lower() != fields.severity.lower():
            return False
    if rule.match_title_regex:
        try:
            if not re.search(rule.match_title_regex, fields.title, re.IGNORECASE):
                return False
        except re.error:
            return False
    return True


def list_alert_rules(tenant_id: str) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(AlertRule)
            .where(AlertRule.tenant_id == tenant_id)
            .order_by(col(AlertRule.priority), col(AlertRule.name))
        ).all()
    return [_serialize_rule(r) for r in rows]


def _serialize_rule(rule: AlertRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "tenant_id": rule.tenant_id,
        "name": rule.name,
        "match_service": rule.match_service,
        "match_severity": rule.match_severity,
        "match_title_regex": rule.match_title_regex,
        "group_window_sec": rule.group_window_sec,
        "action": rule.action,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _get_bucket(session: Session, fingerprint: str) -> AlertGroupBucket | None:
    return session.get(AlertGroupBucket, fingerprint)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _within_window(bucket: AlertGroupBucket, window_sec: int) -> bool:
    if not bucket or not bucket.last_seen_at:
        return False
    delta = datetime.now(timezone.utc) - _as_utc(bucket.last_seen_at)
    return delta.total_seconds() <= max(0, window_sec)


def evaluate_alert_ingest(
    *,
    tenant_id: str,
    source: str,
    log_text: str,
    payload: dict | None = None,
) -> AlertIngestDecision:
    """Evaluate tenant alert rules before triage. Rules-based only — never ML."""
    fields = extract_alert_fields(payload, source=source, log_text=log_text)
    with Session(engine) as session:
        rules = session.exec(
            select(AlertRule)
            .where(AlertRule.tenant_id == tenant_id, AlertRule.enabled == True)  # noqa: E712
            .order_by(col(AlertRule.priority), col(AlertRule.name))
        ).all()

        matched: AlertRule | None = None
        for rule in rules:
            if _rule_matches(rule, fields):
                matched = rule
                break

        if not matched:
            return AlertIngestDecision(
                proceed=True,
                action=ACTION_CREATE_INCIDENT,
                reason="no_matching_rule",
            )

        rule = matched
        fingerprint = _fingerprint(tenant_id, rule.id, fields)
        bucket = _get_bucket(session, fingerprint)
        window = max(0, int(rule.group_window_sec or 0))

        if rule.action == ACTION_SUPPRESS:
            record_alert_suppressed(source=source, rule_id=rule.id)
            return AlertIngestDecision(
                proceed=False,
                action=ACTION_SUPPRESS,
                rule_id=rule.id,
                rule_name=rule.name,
                reason="suppressed_by_rule",
            )

        if window > 0 and bucket and _within_window(bucket, window):
            bucket.alert_count += 1
            bucket.last_seen_at = datetime.now(timezone.utc)
            session.add(bucket)
            session.commit()
            record_alert_grouped(source=source, rule_id=rule.id)
            return AlertIngestDecision(
                proceed=False,
                action=ACTION_ATTACH_EXISTING,
                rule_id=rule.id,
                rule_name=rule.name,
                incident_id=bucket.incident_id,
                reason="grouped_within_window",
            )

        if rule.action == ACTION_ATTACH_EXISTING and bucket and _within_window(bucket, window):
            bucket.alert_count += 1
            bucket.last_seen_at = datetime.now(timezone.utc)
            session.add(bucket)
            session.commit()
            record_alert_grouped(source=source, rule_id=rule.id)
            return AlertIngestDecision(
                proceed=False,
                action=ACTION_ATTACH_EXISTING,
                rule_id=rule.id,
                rule_name=rule.name,
                incident_id=bucket.incident_id,
                reason="attach_existing_bucket",
            )

        return AlertIngestDecision(
            proceed=True,
            action=rule.action if rule.action != ACTION_ATTACH_EXISTING else ACTION_CREATE_INCIDENT,
            rule_id=rule.id,
            rule_name=rule.name,
            reason="create_new_incident",
        )


def register_grouped_incident(
    *,
    tenant_id: str,
    rule_id: str,
    fields: AlertFields,
    incident_id: int,
    group_window_sec: int,
) -> None:
    """After triage creates an incident, register grouping bucket when window > 0."""
    if group_window_sec <= 0:
        return
    fingerprint = _fingerprint(tenant_id, rule_id, fields)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        bucket = _get_bucket(session, fingerprint)
        if bucket:
            bucket.incident_id = incident_id
            bucket.last_seen_at = now
            bucket.alert_count += 1
        else:
            bucket = AlertGroupBucket(
                id=fingerprint,
                tenant_id=tenant_id,
                rule_id=rule_id,
                incident_id=incident_id,
                fingerprint=fingerprint,
                last_seen_at=now,
                alert_count=1,
            )
        session.add(bucket)
        session.commit()


def get_rule_for_followup(session: Session, rule_id: str, tenant_id: str) -> AlertRule | None:
    rule = session.get(AlertRule, rule_id)
    if not rule or rule.tenant_id != tenant_id:
        return None
    return rule


def cleanup_expired_buckets(max_age_sec: int = 86400) -> int:
    """Remove stale group buckets (housekeeping)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_sec)
    removed = 0
    with Session(engine) as session:
        rows = session.exec(select(AlertGroupBucket)).all()
        for row in rows:
            if row.last_seen_at and row.last_seen_at < cutoff:
                session.delete(row)
                removed += 1
        session.commit()
    return removed
