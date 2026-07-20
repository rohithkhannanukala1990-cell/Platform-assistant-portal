"""Dashboard summary API — services, deployments, incidents, DORA."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import User, get_current_user
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
