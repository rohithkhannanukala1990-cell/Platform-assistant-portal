"""Change management service — risk, blast radius, ServiceNow/Jira submission."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..auth import User, write_audit
from ..db.core import engine
from ..db.models.access import ChangeRecord

TIER_ONE_TAGS = {"tier-1", "tier1", "critical", "prod-tier-1"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def transitive_dependents(
    session: Session, tenant_id: str, root_entity_id: str, *, max_depth: int = 5
) -> list[dict[str, Any]]:
    """BFS ServiceDependency to find services depending (transitively) on root.

    Returns list of {id, name, kind, tier, depth} ordered by depth.
    """
    from ..routers.catalog import CatalogEntity, ServiceDependency

    if not root_entity_id:
        return []

    visited: set[str] = {root_entity_id}
    frontier: list[tuple[str, int]] = [(root_entity_id, 0)]
    edges = list(
        session.exec(
            select(ServiceDependency)
        ).all()
    )
    edge_index: dict[str, list[str]] = {}
    for e in edges:
        # A "depends on B" — B is upstream; dependents are the reverse direction:
        # if from → to (calls), a change to `to` affects `from`. So we walk from
        # target back to source.
        edge_index.setdefault(e.to_entity_id, []).append(e.from_entity_id)

    entity_index: dict[str, CatalogEntity] = {}
    rows = list(
        session.exec(
            select(CatalogEntity).where(CatalogEntity.tenant_id == tenant_id)
        ).all()
    )
    for row in rows:
        entity_index[row.id] = row

    out: list[dict[str, Any]] = []
    while frontier:
        node, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        neighbours = edge_index.get(node, [])
        for nb in neighbours:
            if nb in visited:
                continue
            visited.add(nb)
            row = entity_index.get(nb)
            if row is None:
                continue
            tags: list[str] = []
            try:
                tags = json.loads(row.tags or "[]")
            except Exception:
                tags = []
            out.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "kind": row.kind,
                    "tier": _tier_from_tags(tags),
                    "depth": depth + 1,
                }
            )
            frontier.append((nb, depth + 1))
    return out


def _tier_from_tags(tags: list[str]) -> str:
    low = {str(t).lower() for t in tags or []}
    if low & TIER_ONE_TAGS:
        return "tier-1"
    if any("tier-2" in x or "tier2" in x for x in low):
        return "tier-2"
    if any("tier-3" in x or "tier3" in x for x in low):
        return "tier-3"
    return "unknown"


def assess_risk(
    *,
    destroy_count: int = 0,
    root_tier: str = "unknown",
    within_business_hours: bool | None = None,
    recent_incident_within_days: int | None = None,
    change_type: str = "deploy",
) -> str:
    """Return low | moderate | high based on simple rules."""
    if destroy_count and destroy_count > 0:
        return "high"
    if root_tier == "tier-1":
        return "high"
    if recent_incident_within_days is not None and recent_incident_within_days <= 7:
        return "high"
    if change_type == "migration":
        return "high"
    if within_business_hours is False:
        return "moderate"
    if root_tier == "tier-2":
        return "moderate"
    return "low"


def draft_change_record(
    *,
    tenant_id: str,
    workspace_id: str | None,
    change_type: str,
    source_run_id: str | None,
    source_artifact_id: str | None,
    title: str,
    description: str,
    entity_id: str | None = None,
    entity_name: str | None = None,
    root_tier: str | None = None,
    destroy_count: int = 0,
    rollback_plan: str = "",
    within_business_hours: bool | None = None,
    recent_incident_within_days: int | None = None,
) -> ChangeRecord:
    with Session(engine) as session:
        # Blast radius via transitive dependents
        radius = transitive_dependents(session, tenant_id, entity_id or "") if entity_id else []
        # Root tier from catalog if not supplied
        rt = root_tier
        if not rt and entity_id:
            from ..routers.catalog import CatalogEntity

            row = session.get(CatalogEntity, entity_id)
            if row:
                try:
                    tags = json.loads(row.tags or "[]")
                except Exception:
                    tags = []
                rt = _tier_from_tags(tags)
        rt = rt or "unknown"

        # Check recent incidents on the same service
        if recent_incident_within_days is None and entity_name:
            from ..db.models.ops import Incident

            cutoff = _now() - timedelta(days=7)
            recent = session.exec(
                select(Incident).where(
                    Incident.tenant_id == tenant_id,
                    Incident.timestamp >= cutoff,
                )
            ).all()
            hit = any(
                entity_name.lower() in (r.summary or "").lower()
                or entity_name.lower() in (r.root_cause or "").lower()
                for r in recent
            )
            recent_incident_within_days = 3 if hit else None

        # Business hours default → based on now
        wbh = within_business_hours
        if wbh is None:
            wbh = 9 <= _now().hour < 17

        risk = assess_risk(
            destroy_count=destroy_count,
            root_tier=rt,
            within_business_hours=wbh,
            recent_incident_within_days=recent_incident_within_days,
            change_type=change_type,
        )

        record = ChangeRecord(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            change_type=change_type,
            source_run_id=source_run_id,
            source_artifact_id=source_artifact_id,
            title=title,
            description=description,
            risk=risk,
            blast_radius_json=json.dumps(
                {
                    "root_entity_id": entity_id,
                    "root_entity_name": entity_name,
                    "root_tier": rt,
                    "dependent_services": radius,
                    "dependent_count": len(radius),
                    "destroy_count": destroy_count,
                    "within_business_hours": wbh,
                    "recent_incident_within_days": recent_incident_within_days,
                },
                default=str,
            ),
            rollback_plan=rollback_plan or "",
            status="draft",
        )
        session.add(record)
        session.commit()
        session.refresh(record)

    write_audit(
        "system",
        "System",
        "change_drafted",
        resource=f"change:{record.id}",
        detail=f"type={change_type} risk={risk} entity={entity_name or entity_id}",
    )
    return record


async def submit_change_request(
    *,
    change_id: str,
    tenant_id: str,
    actor: str,
    user: User,
) -> dict[str, Any]:
    """Push to ServiceNow (preferred) or Jira, store external_id/url."""
    from ..connectors.idempotency import ConnectorNotConfigured
    from .servicenow_access import try_servicenow_connector_for_user

    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if not record or record.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if record.status in {"submitted", "approved"}:
            return {
                "ok": True,
                "idempotent": True,
                "external_id": record.external_id,
                "external_url": record.external_url,
            }

    snow = None
    try:
        snow = try_servicenow_connector_for_user(user, tenant_id=tenant_id)
    except Exception:
        snow = None

    idem = f"change-submit:{change_id}"
    if snow is not None:
        try:
            result = await snow.create_change_request(
                short_description=record.title[:160] or "Platform change",
                description=record.description or "",
                risk=record.risk or "moderate",
                idempotency_key=idem,
            )
        except ConnectorNotConfigured as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:400]}
        ext_id = result.get("sys_id") or result.get("number")
        ext_url = result.get("url")
    else:
        # Fallback: create a Jira issue if Jira is connected
        from .jira_access import try_jira_connector_for_user

        jira = try_jira_connector_for_user(user, tenant_id=tenant_id)
        if jira is None:
            return {"ok": False, "error": "no_change_system_connected"}
        try:
            result = await jira.create_issue(
                project_key=None,
                summary=record.title[:200] or "Platform change",
                description=record.description or "",
                issue_type="Task",
                idempotency_key=idem,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:400]}
        ext_id = (result or {}).get("key")
        ext_url = (result or {}).get("url")

    now = _now()
    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if record:
            record.external_id = str(ext_id or "")
            record.external_url = ext_url
            record.status = "submitted"
            record.submitted_at = now
            session.add(record)
            session.commit()
            session.refresh(record)

    write_audit(
        actor,
        "Admin",
        "change_submitted",
        resource=f"change:{change_id}",
        detail=f"external_id={ext_id}",
    )
    return {"ok": True, "external_id": ext_id, "external_url": ext_url}


def mark_change_approved(*, change_id: str, tenant_id: str, actor: str) -> dict[str, Any]:
    """Test/local hook to move ChangeRecord to approved without an external call."""
    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if not record or record.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        record.status = "approved"
        record.approved_at = _now()
        session.add(record)
        session.commit()
    write_audit(
        actor,
        "Admin",
        "change_approved",
        resource=f"change:{change_id}",
        detail="approved (local)",
    )
    return {"ok": True}


def reject_change_record(*, change_id: str, tenant_id: str, actor: str, reason: str = "") -> dict[str, Any]:
    """Reject a draft/submitted change — mirrors mark_change_approved's shape."""
    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if not record or record.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if record.status not in {"draft", "submitted"}:
            return {"ok": False, "error": f"status={record.status}"}
        record.status = "rejected"
        session.add(record)
        session.commit()
    write_audit(
        actor,
        "Admin",
        "change_rejected",
        resource=f"change:{change_id}",
        detail=(reason or "rejected")[:500],
    )
    return {"ok": True}


async def check_change_approved(
    *, change_id: str, tenant_id: str, user: User
) -> dict[str, Any]:
    """Poll external system for approval — best-effort. If no external record,
    reflect stored status."""
    from .servicenow_access import try_servicenow_connector_for_user

    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if not record or record.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        if not record.external_id:
            return {"ok": True, "status": record.status}

    snow = try_servicenow_connector_for_user(user, tenant_id=tenant_id)
    if snow is None:
        return {"ok": True, "status": record.status, "note": "servicenow_disconnected"}

    # Simplified: rely on execute_action if implemented; otherwise no-op.
    try:
        result = await snow.execute_action(
            "get_change_state", {"sys_id": record.external_id}
        )
    except Exception:
        result = {"ok": False}
    return {"ok": True, "status": record.status, "external": result}


def close_change_request(
    *,
    change_id: str,
    tenant_id: str,
    outcome: str,
    actor: str,
    implemented_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Close the change and link any incident that occurred within 2 hours of
    implemented_at."""
    from ..db.models.ops import Incident

    now = _now()
    with Session(engine) as session:
        record = session.get(ChangeRecord, change_id)
        if not record or record.tenant_id != tenant_id:
            return {"ok": False, "error": "not_found"}
        impl = implemented_at or record.implemented_at or now
        record.implemented_at = impl
        record.outcome = outcome
        window_start = impl
        window_end = impl + timedelta(hours=2)
        candidate = session.exec(
            select(Incident).where(
                Incident.tenant_id == tenant_id,
                col(Incident.timestamp) >= window_start,
                col(Incident.timestamp) <= window_end,
            )
        ).first()
        if candidate is not None:
            record.incident_id = candidate.id
        record.status = "closed"
        record.closed_at = now
        session.add(record)
        session.commit()
        session.refresh(record)

    write_audit(
        actor,
        "Admin",
        "change_closed",
        resource=f"change:{change_id}",
        detail=f"outcome={outcome} incident={record.incident_id}",
    )
    return {
        "ok": True,
        "change_id": change_id,
        "incident_id": record.incident_id,
        "outcome": outcome,
    }
