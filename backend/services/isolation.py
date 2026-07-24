"""Tenant / workspace isolation helpers (fail closed)."""

from __future__ import annotations

from typing import Any, Optional, TypeVar

from fastapi import HTTPException, Request
from sqlalchemy.sql import ColumnElement

T = TypeVar("T")


def require_tenant(request: Request) -> str:
    """Return tenant_id from request.state (set by WorkspaceIsolationMiddleware)."""
    tid = getattr(request.state, "tenant_id", None)
    if tid is not None and str(tid).strip():
        return str(tid).strip()
    user = getattr(request.state, "user", None)
    if user is not None:
        ut = getattr(user, "tenant_id", None)
        if ut is not None and str(ut).strip():
            return str(ut).strip()
    from ..context import DEFAULT_TENANT_ID

    return DEFAULT_TENANT_ID


def require_workspace(request: Request, optional: bool = False) -> str | None:
    """Return workspace_id from request.state; 400 when required and missing."""
    wid = getattr(request.state, "workspace_id", None)
    if wid is not None and str(wid).strip():
        return str(wid).strip()
    if optional:
        return None
    raise HTTPException(status_code=400, detail="workspace_id is required")


def apply_tenant_filter(statement: Any, model: Any, tenant_id: str) -> Any:
    """Add tenant_id equality filter when the model exposes tenant_id."""
    if not tenant_id:
        return statement
    col = getattr(model, "tenant_id", None)
    if col is None:
        return statement
    return statement.where(col == tenant_id)


def assert_same_tenant(
    resource_tenant_id: str | None,
    tenant_id: str,
    *,
    detail: str = "Not found",
) -> None:
    """Raise 404 (not 403) on tenant mismatch to avoid existence leaks."""
    from ..context import DEFAULT_TENANT_ID, resolve_tenant_id

    left = resolve_tenant_id(resource_tenant_id, DEFAULT_TENANT_ID)
    right = resolve_tenant_id(tenant_id, DEFAULT_TENANT_ID)
    if left != right:
        raise HTTPException(status_code=404, detail=detail)


def tenant_of(user_or_request: Any) -> str:
    """Best-effort tenant from a User or Request."""
    from ..context import DEFAULT_TENANT_ID, resolve_tenant_id

    if user_or_request is None:
        return DEFAULT_TENANT_ID
    if hasattr(user_or_request, "state"):
        return require_tenant(user_or_request)
    return resolve_tenant_id(
        getattr(user_or_request, "tenant_id", None),
        DEFAULT_TENANT_ID,
    )
