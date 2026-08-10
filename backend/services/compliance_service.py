"""Compliance evidence collection — SOC2 control → portal data source mapping."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..db.core import engine

CONTROLS: dict[str, dict[str, str]] = {
    "SOC2-CC6.1": {
        "name": "Logical access controls",
        "description": "Access is granted based on documented approvals and MFA",
    },
    "SOC2-CC6.2": {
        "name": "Access is removed when no longer needed",
        "description": "Provisioned access is expired, revoked, or reviewed within 90 days",
    },
    "SOC2-CC6.3": {
        "name": "Least privilege",
        "description": "Users hold only the permissions their role template allows",
    },
    "SOC2-CC7.2": {
        "name": "System monitoring",
        "description": "Tier-1 services have alerts and incidents are tracked",
    },
    "SOC2-CC8.1": {
        "name": "Change management",
        "description": "Production changes have approval records",
    },
    "SOC2-CC7.4": {
        "name": "Incident response",
        "description": "High-severity incidents have postmortems within 7 days",
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """Normalize possibly-naive SQLite datetimes to UTC-aware."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def collect_evidence(
    *, control_id: str, tenant_id: str, period_start: datetime, period_end: datetime
) -> dict[str, Any]:
    """Return {evidence: [...], gaps: [...]} for a single control."""
    if control_id == "SOC2-CC6.1":
        return _cc6_1(tenant_id, period_start, period_end)
    if control_id == "SOC2-CC6.2":
        return _cc6_2(tenant_id, period_start, period_end)
    if control_id == "SOC2-CC6.3":
        return _cc6_3(tenant_id, period_start, period_end)
    if control_id == "SOC2-CC7.2":
        return _cc7_2(tenant_id, period_start, period_end)
    if control_id == "SOC2-CC8.1":
        return _cc8_1(tenant_id, period_start, period_end)
    if control_id == "SOC2-CC7.4":
        return _cc7_4(tenant_id, period_start, period_end)
    return {"evidence": [], "gaps": []}


def _cc6_1(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    """Logical access controls — grants + MFA enrollment. Gap: admin w/o MFA."""
    from ..auth import User
    from ..db.models.access import AccessRequestRecord

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    with Session(engine) as session:
        grants = list(
            session.exec(
                select(AccessRequestRecord).where(
                    AccessRequestRecord.tenant_id == tenant_id,
                    col(AccessRequestRecord.created_at) >= ps,
                    col(AccessRequestRecord.created_at) <= pe,
                )
            ).all()
        )
        for g in grants:
            evidence.append(
                {
                    "type": "access_grant",
                    "id": g.id,
                    "subject": g.subject_username,
                    "resource": f"{g.resource_type}:{g.resource_id}",
                    "approved_by": g.approved_by,
                    "status": g.status,
                    "created_at": g.created_at.isoformat() if g.created_at else None,
                }
            )
        users = list(
            session.exec(
                select(User).where(User.tenant_id == tenant_id)
            ).all()
        )
        for u in users:
            role = (u.role or "").lower()
            if role in {"admin", "administrator"} and not bool(u.mfa_enabled):
                gaps.append(
                    {
                        "control": "SOC2-CC6.1",
                        "type": "admin_without_mfa",
                        "username": u.username,
                        "detail": "Admin role user has MFA disabled",
                    }
                )
            evidence.append(
                {
                    "type": "user_mfa",
                    "username": u.username,
                    "role": u.role,
                    "mfa_enabled": bool(u.mfa_enabled),
                }
            )
    return {"evidence": evidence, "gaps": gaps}


def _cc6_2(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    from ..db.models.access import AccessRequestRecord

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    with Session(engine) as session:
        removed = list(
            session.exec(
                select(AccessRequestRecord).where(
                    AccessRequestRecord.tenant_id == tenant_id,
                    col(AccessRequestRecord.status).in_(["expired", "revoked"]),
                )
            ).all()
        )
        for r in removed:
            evidence.append(
                {
                    "type": "access_removal",
                    "id": r.id,
                    "subject": r.subject_username,
                    "resource": f"{r.resource_type}:{r.resource_id}",
                    "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                    "reason": r.status,
                }
            )
        stale_cutoff = _now() - timedelta(days=90)
        stale = list(
            session.exec(
                select(AccessRequestRecord).where(
                    AccessRequestRecord.tenant_id == tenant_id,
                    AccessRequestRecord.status == "provisioned",
                    col(AccessRequestRecord.provisioned_at) <= stale_cutoff,
                )
            ).all()
        )
        for r in stale:
            gaps.append(
                {
                    "control": "SOC2-CC6.2",
                    "type": "stale_access",
                    "access_request_id": r.id,
                    "subject": r.subject_username,
                    "resource": f"{r.resource_type}:{r.resource_id}",
                    "provisioned_at": r.provisioned_at.isoformat()
                    if r.provisioned_at
                    else None,
                }
            )
    return {"evidence": evidence, "gaps": gaps}


def _cc6_3(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    from ..db.models.access import AccessRequestRecord
    from ..db.models.rbac_tables import UserRole

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    with Session(engine) as session:
        assigns = list(session.exec(select(UserRole)).all())
        for a in assigns:
            evidence.append(
                {
                    "type": "role_assignment",
                    "user_id": a.user_id,
                    "role_id": a.role_id,
                }
            )
        grants = list(
            session.exec(
                select(AccessRequestRecord).where(
                    AccessRequestRecord.tenant_id == tenant_id
                )
            ).all()
        )
        # Gap: policy_assessment recommended reject/broad but request was provisioned
        for g in grants:
            if g.status != "provisioned":
                continue
            try:
                assessment = json.loads(g.policy_assessment_json or "{}")
            except Exception:
                assessment = {}
            rec = str(assessment.get("recommendation") or "").lower()
            if rec.startswith("reject") or rec == "review_broad_access":
                gaps.append(
                    {
                        "control": "SOC2-CC6.3",
                        "type": "least_privilege_violation",
                        "access_request_id": g.id,
                        "subject": g.subject_username,
                        "resource": f"{g.resource_type}:{g.resource_id}",
                        "policy_recommendation": rec,
                    }
                )
    return {"evidence": evidence, "gaps": gaps}


def _cc7_2(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    from ..db.models.alerts import AlertRule
    from ..db.models.ops import Incident
    from ..routers.catalog import CatalogEntity

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    with Session(engine) as session:
        rules = list(session.exec(select(AlertRule)).all())
        for r in rules:
            evidence.append(
                {
                    "type": "alert_rule",
                    "id": r.id,
                    "name": getattr(r, "name", ""),
                }
            )
        incidents = list(
            session.exec(
                select(Incident).where(
                    Incident.tenant_id == tenant_id,
                    col(Incident.timestamp) >= ps,
                    col(Incident.timestamp) <= pe,
                )
            ).all()
        )
        for i in incidents:
            evidence.append(
                {
                    "type": "incident",
                    "id": i.id,
                    "severity": i.severity,
                    "status": i.status,
                    "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                }
            )
        # Gap: tier-1 catalog service with no alert rule mentioning its name
        services = list(
            session.exec(
                select(CatalogEntity).where(
                    CatalogEntity.tenant_id == tenant_id,
                    CatalogEntity.kind == "Service",
                )
            ).all()
        )
        for svc in services:
            try:
                tags = json.loads(svc.tags or "[]")
            except Exception:
                tags = []
            low = {str(t).lower() for t in tags}
            is_tier1 = bool({"tier-1", "tier1", "critical"} & low)
            if not is_tier1:
                continue
            hay = " ".join(
                str(getattr(r, "name", "")).lower() for r in rules
            )
            if svc.name.lower() not in hay:
                gaps.append(
                    {
                        "control": "SOC2-CC7.2",
                        "type": "tier1_no_alert",
                        "entity_id": svc.id,
                        "service": svc.name,
                    }
                )
    return {"evidence": evidence, "gaps": gaps}


def _cc8_1(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    """Change management — deploy/terraform_apply must have an approved
    ChangeRecord."""
    from ..db.models.access import ChangeRecord
    from ..services.artifact_service import ArtifactApproval

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    change_methods = {
        ("terraform", "apply_plan"),
        ("sql", "execute_migration"),
        ("kubernetes", "deploy"),
        ("kubernetes", "apply"),
        ("kubernetes", "rollout"),
    }
    with Session(engine) as session:
        records = list(
            session.exec(
                select(ChangeRecord).where(
                    ChangeRecord.tenant_id == tenant_id,
                    col(ChangeRecord.created_at) >= ps,
                    col(ChangeRecord.created_at) <= pe,
                )
            ).all()
        )
        approved_ids = {r.source_artifact_id for r in records if r.status == "approved"}
        for r in records:
            evidence.append(
                {
                    "type": "change_record",
                    "id": r.id,
                    "status": r.status,
                    "risk": r.risk,
                    "external_id": r.external_id,
                }
            )
        approvals = list(
            session.exec(
                select(ArtifactApproval).where(
                    ArtifactApproval.tenant_id == tenant_id,
                    col(ArtifactApproval.created_at) >= ps,
                    col(ArtifactApproval.created_at) <= pe,
                )
            ).all()
        )
        for a in approvals:
            if (a.connector, a.method) not in change_methods:
                continue
            if a.status != "approved":
                continue
            if a.id not in approved_ids:
                gaps.append(
                    {
                        "control": "SOC2-CC8.1",
                        "type": "change_without_record",
                        "artifact_approval_id": a.id,
                        "connector": a.connector,
                        "method": a.method,
                    }
                )
    return {"evidence": evidence, "gaps": gaps}


def _cc7_4(tenant_id: str, ps: datetime, pe: datetime) -> dict[str, Any]:
    """Incident response — high-severity incidents must have a postmortem within 7d."""
    from ..db.models.ops import Incident, IncidentPostmortem

    evidence: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    with Session(engine) as session:
        incidents = list(
            session.exec(
                select(Incident).where(
                    Incident.tenant_id == tenant_id,
                    col(Incident.timestamp) >= ps,
                    col(Incident.timestamp) <= pe,
                )
            ).all()
        )
        postmortems = list(
            session.exec(
                select(IncidentPostmortem).where(
                    IncidentPostmortem.tenant_id == tenant_id
                )
            ).all()
        )
        pm_by_incident: dict[int, IncidentPostmortem] = {}
        for p in postmortems:
            pm_by_incident.setdefault(p.incident_id, p)
        now = _now()
        for i in incidents:
            evidence.append(
                {
                    "type": "incident",
                    "id": i.id,
                    "severity": i.severity,
                    "status": i.status,
                    "postmortem_present": i.id in pm_by_incident,
                }
            )
            sev = (i.severity or "").lower()
            high = sev in {"critical", "high", "sev1", "p1", "sev-1", "1", "sev2", "p2"}
            if not high:
                continue
            ts = _aware(i.timestamp) or now
            age = now - ts
            if age >= timedelta(days=7) and i.id not in pm_by_incident:
                gaps.append(
                    {
                        "control": "SOC2-CC7.4",
                        "type": "high_severity_no_postmortem",
                        "incident_id": i.id,
                        "severity": i.severity,
                        "age_days": age.days,
                    }
                )
    return {"evidence": evidence, "gaps": gaps}


def collect_all_controls(
    *, tenant_id: str, period_start: datetime, period_end: datetime
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for cid in CONTROLS:
        out[cid] = collect_evidence(
            control_id=cid,
            tenant_id=tenant_id,
            period_start=period_start,
            period_end=period_end,
        )
    return out


def scan_gaps(
    *, tenant_id: str, period_start: datetime, period_end: datetime
) -> list[dict[str, Any]]:
    """Return a prioritised list of gaps across all controls."""
    results = collect_all_controls(
        tenant_id=tenant_id, period_start=period_start, period_end=period_end
    )
    priorities = {
        "SOC2-CC6.1": 1,
        "SOC2-CC8.1": 1,
        "SOC2-CC7.4": 2,
        "SOC2-CC6.2": 3,
        "SOC2-CC6.3": 3,
        "SOC2-CC7.2": 4,
    }
    flat: list[dict[str, Any]] = []
    for cid, res in results.items():
        for g in res.get("gaps") or []:
            flat.append({**g, "priority": priorities.get(cid, 5)})
    flat.sort(key=lambda x: x.get("priority", 9))
    return flat


def build_evidence_pack(
    *,
    tenant_id: str,
    period_start: datetime,
    period_end: datetime,
    collected_by: str,
) -> bytes:
    """Build a ZIP: one JSON per control + summary.json + summary.txt."""
    results = collect_all_controls(
        tenant_id=tenant_id, period_start=period_start, period_end=period_end
    )
    buf = io.BytesIO()
    summary = {
        "tenant_id": tenant_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "collected_by": collected_by,
        "collected_at": _now().isoformat(),
        "controls": {},
    }
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid, res in results.items():
            evidence_count = len(res.get("evidence") or [])
            gap_count = len(res.get("gaps") or [])
            summary["controls"][cid] = {
                "name": CONTROLS[cid]["name"],
                "evidence_count": evidence_count,
                "gap_count": gap_count,
            }
            zf.writestr(
                f"{cid}.json",
                json.dumps(
                    {"control": cid, "name": CONTROLS[cid]["name"], **res},
                    default=str,
                    indent=2,
                ),
            )
        summary_lines = ["Compliance Evidence Pack", "=" * 40]
        summary_lines.append(f"Tenant: {tenant_id}")
        summary_lines.append(f"Period: {period_start.isoformat()} → {period_end.isoformat()}")
        summary_lines.append(f"Collected by: {collected_by}")
        summary_lines.append("")
        for cid, info in summary["controls"].items():
            summary_lines.append(
                f"{cid} ({info['name']}): {info['evidence_count']} evidence, "
                f"{info['gap_count']} gap(s)"
            )
        zf.writestr("summary.json", json.dumps(summary, default=str, indent=2))
        zf.writestr("summary.txt", "\n".join(summary_lines))
    return buf.getvalue()


def persist_evidence_run(
    *,
    tenant_id: str,
    control_results: dict[str, dict[str, Any]],
    period_start: datetime,
    period_end: datetime,
    collected_by: str,
) -> list[str]:
    """Save one ControlEvidence row per control. Returns list of row ids."""
    from ..db.models.access import ControlEvidence

    now = _now()
    ids: list[str] = []
    with Session(engine) as session:
        for cid, res in control_results.items():
            row = ControlEvidence(
                tenant_id=tenant_id,
                control_id=cid,
                control_name=CONTROLS.get(cid, {}).get("name", ""),
                period_start=period_start,
                period_end=period_end,
                evidence_json=json.dumps(res.get("evidence") or [], default=str),
                gap_count=len(res.get("gaps") or []),
                gaps_json=json.dumps(res.get("gaps") or [], default=str),
                collected_at=now,
                collected_by=collected_by,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            ids.append(row.id)
    return ids
