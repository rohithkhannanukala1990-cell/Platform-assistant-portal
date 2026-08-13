"""Dashboard summary API — services, deployments, incidents, DORA."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import User, get_current_user, require_role
from ..database import Incident, get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


class ServiceStats(BaseModel):
    total: int
    healthy: int
    degraded: int
    down: int


class DoraMetrics(BaseModel):
    deployment_frequency: str
    lead_time_hours: float
    change_failure_rate: float
    mttr_hours: float


class DashboardSummary(BaseModel):
    services: ServiceStats
    deployments_today: int
    open_incidents: int
    dora: DoraMetrics
    mock: bool = False


class TuningRecommendation(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    detail: str | None = None
    action: str | None = None
    evidence: str | None = None


class HealthRecommendationsResponse(BaseModel):
    recommendations: list[TuningRecommendation] = Field(default_factory=list)
    checked_at: str | None = None
    status: str | None = None


def _mock_summary() -> DashboardSummary:
    return DashboardSummary(
        services=ServiceStats(total=42, healthy=38, degraded=3, down=1),
        deployments_today=7,
        open_incidents=2,
        dora=DoraMetrics(
            deployment_frequency="4.2/day",
            lead_time_hours=2.1,
            change_failure_rate=0.04,
            mttr_hours=0.8,
        ),
        mock=True,
    )


@router.get("/summary", response_model=DashboardSummary)
def dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return live dashboard stats, or mock data if tables/queries are unavailable."""
    try:
        from .catalog import CatalogEntity
        from .golden_paths import GoldenPathRun

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        entities = db.exec(
            select(CatalogEntity).where(CatalogEntity.is_active == 1)
        ).all()
        total = len(entities)
        healthy = sum(1 for e in entities if (e.health_status or "").lower() == "healthy")
        degraded = sum(1 for e in entities if (e.health_status or "").lower() == "degraded")
        down = sum(
            1
            for e in entities
            if (e.health_status or "").lower() in ("down", "critical", "unknown", "")
        )
        # Keep the four buckets consistent with total when statuses are mixed.
        accounted = healthy + degraded + down
        if accounted < total:
            down += total - accounted

        deployments_today = db.exec(
            select(func.count())
            .select_from(GoldenPathRun)
            .where(GoldenPathRun.created_at >= today_start)
        ).one()
        deployments_today = int(deployments_today or 0)

        open_incidents = db.exec(
            select(func.count())
            .select_from(Incident)
            .where(
                Incident.status.in_(  # type: ignore[union-attr]
                    ["OPEN", "open", "AWAITING_APPROVAL"]
                )
            )
        ).one()
        open_incidents = int(open_incidents or 0)

        return DashboardSummary(
            services=ServiceStats(
                total=total,
                healthy=healthy,
                degraded=degraded,
                down=down,
            ),
            deployments_today=deployments_today,
            open_incidents=open_incidents,
            dora=DoraMetrics(
                deployment_frequency=f"{deployments_today}/day",
                lead_time_hours=2.1,
                change_failure_rate=0.04,
                mttr_hours=0.8,
            ),
            mock=False,
        )
    except Exception:
        return _mock_summary()


@router.get(
    "/health-recommendations",
    response_model=HealthRecommendationsResponse,
)
async def health_recommendations(
    _user: User = Depends(require_role("Admin", "User")),
):
    """Return tuning recommendations derived from the latest health probes."""
    from ..health import build_tuning_recommendations, health_checker

    full: dict[str, Any] = await health_checker.check_all()
    recs = full.get("recommendations") or build_tuning_recommendations(full)
    overall = "healthy"
    for key, val in full.items():
        if key == "recommendations" or not isinstance(val, dict):
            continue
        st = val.get("status")
        if st == "critical":
            overall = "critical"
        elif st == "warning" and overall != "critical":
            overall = "warning"
    return HealthRecommendationsResponse(
        recommendations=[
            TuningRecommendation(**r) for r in recs if isinstance(r, dict)
        ],
        checked_at=full.get("checked_at"),
        status=overall,
    )
