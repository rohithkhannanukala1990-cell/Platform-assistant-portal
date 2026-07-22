"""Workspace / tenant isolation middleware.

Resolves workspace_id and tenant_id for each request and attaches them to
``request.state`` so downstream routers can scope queries consistently.

Sources (in order of preference for workspace):
1. ``X-Workspace-Id`` header (active workspace switcher)
2. Authenticated user's ``workspace_id`` (default workspace)
3. ``None`` in demo / single-tenant setups

Tenant comes from the user record, ``X-Tenant-Id``, or ``DEFAULT_TENANT_ID``.
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from backend.context import DEFAULT_TENANT_ID, PlatformContext, resolve_tenant_id

# Paths that never require an active workspace (auth, health, docs, static).
_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/health",
    "/ready",
    "/live",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/auth/",
    "/api/auth/",
    "/favicon",
)


def _is_public_path(path: str) -> bool:
    if path == "/" or path == "":
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True
    return False


def _enforce_workspace_required() -> bool:
    """Optional hard reject when workspace is missing outside demo/dev."""
    flag = (os.getenv("ENFORCE_WORKSPACE_ISOLATION") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    # In non-dev environments, enable soft enforcement only when explicitly opted in
    # via the flag above. Demo/single-tenant stays working by default.
    return False


def _load_user_from_authorization(authorization: str | None):
    """Best-effort attach of User from Bearer token (middleware runs before Depends)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        from backend.auth import User, decode_token, engine
    except Exception:
        return None
    try:
        payload = decode_token(token)
        username = str(payload.get("sub") or "")
        if not username:
            return None
        with Session(engine) as session:
            return session.exec(select(User).where(User.username == username)).first()
    except Exception:
        return None


# TODO(S2-P2.1): Enforce workspace isolation from authenticated user context
class WorkspaceIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        if user is None:
            user = _load_user_from_authorization(request.headers.get("Authorization"))
            if user is not None:
                request.state.user = user

        header_workspace = (request.headers.get("X-Workspace-Id") or "").strip()
        # Frontend sends "default" when no workspace is selected — treat as unset.
        if header_workspace.lower() in ("", "default", "none", "null"):
            header_workspace = ""

        user_workspace = None
        if user is not None:
            raw = getattr(user, "workspace_id", None)
            if raw is not None and str(raw).strip():
                user_workspace = str(raw).strip()

        workspace_id = header_workspace or user_workspace or None

        tenant_id = resolve_tenant_id(
            getattr(user, "tenant_id", None) if user is not None else None,
            request.headers.get("X-Tenant-Id"),
            request.headers.get("X-Org-Id"),
            DEFAULT_TENANT_ID,
        )

        request.state.workspace_id = workspace_id
        request.state.tenant_id = tenant_id

        try:
            from backend.observability.logger import set_request_context

            set_request_context(workspace_id=workspace_id)
        except Exception:
            pass

        # Optionally reject authenticated API calls without a workspace outside demos.
        if (
            _enforce_workspace_required()
            and not PlatformContext.is_dev_environment()
            and not _is_public_path(request.url.path)
            and user is not None
            and not workspace_id
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "workspace_id is required",
                    "code": "workspace_required",
                },
            )

        return await call_next(request)
