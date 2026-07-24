"""Read-only Kubernetes operations for the authenticated user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import User, get_current_user
from ..connectors.kubernetes_connector import KubernetesConnector
from ..services.k8s_access import k8s_connector_for_user

router = APIRouter(prefix="/api/k8s", tags=["k8s"])


def _connector(user: User) -> KubernetesConnector:
    return k8s_connector_for_user(user)


@router.get("/namespaces")
async def api_k8s_namespaces(current_user: User = Depends(get_current_user)):
    connector = _connector(current_user)
    return await connector.list_namespaces()


@router.get("/pods")
async def api_k8s_pods(
    namespace: str = Query(default="default"),
    current_user: User = Depends(get_current_user),
):
    connector = _connector(current_user)
    return await connector.list_pods(namespace=namespace)


@router.get("/nodes")
async def api_k8s_nodes(current_user: User = Depends(get_current_user)):
    connector = _connector(current_user)
    return await connector.list_nodes()
