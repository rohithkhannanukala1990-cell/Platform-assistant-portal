"""Workspace / tenant isolation middleware.

Resolves workspace_id and tenant_id for each request and attaches them to
``request.state`` so downstream routers can scope queries consistently.

Tenant trust rules:
- If the authenticated user has ``tenant_id``, that value ALWAYS wins.
- ``X-Tenant-Id`` / ``X-Org-Id`` are ignored for privilege escalation
  (non-admins cannot switch tenants via header).

Workspace sources (in order):
1. ``X-Workspace-Id`` header (active workspace switcher)
2. Authenticated user's ``workspace_id`` (default workspace)
3. ``None`` when unset

Set ``ENFORCE_WORKSPACE_ISOLATION=true`` to hard-reject authenticated
non-public requests that lack a workspace_id (production-ready path).
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware

from backend.context import DEFAULT_TENANT_ID, resolve_tenant_id

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

# Extra allowlist when enforcement is on (status / LLM probes without workspace).
_ENFORCE_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/api/llm",
    "/api/settings",
    # Admin-only MCP server config, like LLM providers. Tool calls stay enforced.
    "/api/mcp/servers",
)


def _is_public_path(path: str) -> bool:
    if path == "/" or path == "":
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True
    return False


def _is_enforce_allowlisted(path: str) -> bool:
    for prefix in _ENFORCE_ALLOWLIST_PREFIXES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True
    return False


def _enforce_workspace_required() -> bool:
    flag = (os.getenv("ENFORCE_WORKSPACE_ISOLATION") or "").strip().lower()
    return flag in ("1", "true", "yes", "on")


def _is_admin(user) -> bool:
    role = str(getattr(user, "role", "") or "").strip().lower()
    return role in {"admin", "superadmin", "platformadmin"}


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

        # Tenant: never trust client header over the authenticated user's tenant.
        user_tenant = None
        if user is not None:
            raw_t = getattr(user, "tenant_id", None)
            if raw_t is not None and str(raw_t).strip():
                user_tenant = str(raw_t).strip()

        header_tenant = (request.headers.get("X-Tenant-Id") or request.headers.get("X-Org-Id") or "").strip()
        if user_tenant:
            # Admins may optionally override only when explicitly enabled later;
            # default: force bound tenant (no privilege escalation via header).
            if _is_admin(user) and header_tenant and header_tenant != user_tenant:
                # Still ignore header override — keep fail-closed unless product needs it.
                tenant_id = user_tenant
            else:
                tenant_id = user_tenant
        else:
            tenant_id = resolve_tenant_id(header_tenant or None, DEFAULT_TENANT_ID)

        request.state.workspace_id = workspace_id
        request.state.tenant_id = tenant_id

        try:
            from backend.observability.logger import set_request_context

            set_request_context(workspace_id=workspace_id)
        except Exception:
            pass

        if (
            _enforce_workspace_required()
            and not _is_public_path(request.url.path)
            and not _is_enforce_allowlisted(request.url.path)
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
