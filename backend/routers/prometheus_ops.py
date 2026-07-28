"""Prometheus read ops — query metrics + list alerts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import User, get_current_user
from ..connectors.prometheus_connector import PrometheusConnector
from ..services.prometheus_access import prometheus_connector_for_user

router = APIRouter(prefix="/api/prometheus", tags=["prometheus"])


def _connector(user: User) -> PrometheusConnector:
    return prometheus_connector_for_user(user)


@router.get("/alerts")
async def api_prometheus_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    return await _connector(current_user).list_alerts(limit=limit)


@router.get("/query")
async def api_prometheus_query(
    query: str = Query(..., min_length=1),
    current_user: User = Depends(get_current_user),
):
    return await _connector(current_user).query(query)
