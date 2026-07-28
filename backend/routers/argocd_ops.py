"""ArgoCD read ops — application health."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import User, get_current_user
from ..connectors.argocd_connector import ArgoCDConnector
from ..services.argocd_access import argocd_connector_for_user

router = APIRouter(prefix="/api/argocd", tags=["argocd"])


def _connector(user: User) -> ArgoCDConnector:
    return argocd_connector_for_user(user)


@router.get("/applications")
async def api_argocd_applications(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    return await _connector(current_user).list_applications(limit=limit)
