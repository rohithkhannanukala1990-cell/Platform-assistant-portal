"""Health summary, alerts, and auto-heal APIs."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from ..auth import User, require_admin, require_role, write_audit
from ..database import HealthAlert, engine as db_engine
from ..observability.logger import logger

router = APIRouter(tags=["health-api"])


@router.get("/api/health/summary")
async def api_health_summary():
    from ..health import health_checker

    return await health_checker.get_summary()


@router.get("/api/health/full")
async def api_health_full(_user: User = Depends(require_role("Admin", "User"))):
    from ..health import health_checker

    return await health_checker.check_all()


@router.get("/api/health/alerts")
def api_health_alerts(_user: User = Depends(require_role("Admin", "User"))):
    with Session(db_engine) as session:
        rows = session.exec(
            select(HealthAlert)
            .where(HealthAlert.status == "active")
            .order_by(HealthAlert.created_at.desc())
        ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "message": r.message,
            "severity": r.severity,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/api/health/autoheal/all")
async def api_health_autoheal_all(request: Request, _admin: User = Depends(require_admin)):
    from ..auto_heal import auto_healer

    results = await auto_healer.heal_all_low_risk()
    write_audit(
        _admin.username,
        _admin.role,
        "health_autoheal",
        resource="/api/health/autoheal/all",
        detail=f"Ran low-risk auto-heal: {len(results)} action(s)",
        ip_address=request.client.host if request.client else "",
    )
    return {"healed": results, "count": len(results)}


@router.post("/api/health/alerts/email")
async def api_health_alerts_email(request: Request, _admin: User = Depends(require_admin)):
    """Queue / record a team email digest for active health alerts (integration hook)."""
    with Session(db_engine) as session:
        rows = session.exec(
            select(HealthAlert).where(HealthAlert.status == "active")
        ).all()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alerts_email",
        resource="/api/health/alerts/email",
        detail=f"Requested alert email digest for {len(rows)} active alert(s)",
        ip_address=request.client.host if request.client else "",
    )
    logger.info("Health alerts email requested", extra={"count": len(rows), "actor": _admin.username})
    return {"ok": True, "queued": len(rows), "message": "Alert digest recorded for team distribution"}


@router.post("/api/health/alerts/{alert_id}/resolve")
def api_health_alert_resolve(
    request: Request,
    alert_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(db_engine) as session:
        row = session.get(HealthAlert, alert_id)
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        detail_snip = (row.message or "")[:200]
        row.status = "resolved"
        session.add(row)
        session.commit()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alert_resolve",
        resource=f"/api/health/alerts/{alert_id}/resolve",
        detail=detail_snip,
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True}


@router.post("/api/health/alerts/{alert_id}/ignore")
def api_health_alert_ignore(
    request: Request,
    alert_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(db_engine) as session:
        row = session.get(HealthAlert, alert_id)
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        detail_snip = (row.message or "")[:200]
        row.status = "ignored"
        session.add(row)
        session.commit()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alert_ignore",
        resource=f"/api/health/alerts/{alert_id}/ignore",
        detail=detail_snip,
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True}


@router.get("/health")
@router.get("/health/live")
async def health_check():
    """Liveness — process is up (no dependency checks)."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "service": "platform-assistant-portal",
    }


@router.get("/ready")
@router.get("/health/ready")
async def readiness_check():
    """Readiness — database + Redis (when configured / production)."""
    from ..services.readiness import evaluate_readiness

    payload = evaluate_readiness()
    if payload.get("status") != "ready":
        return JSONResponse(status_code=503, content=payload)
    return payload
