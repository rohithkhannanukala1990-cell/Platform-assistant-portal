"""Workspace isolation middleware.

Sets request.state.workspace_id from the authenticated user so downstream
routers can scope queries without repeating the lookup.

NOTE: This middleware requires User.workspace_id to be populated on
request.state.user before dispatch (e.g. via a JWT-decode middleware that
attaches the full user object including their default workspace). Until
User.workspace_id is added to the User model and the auth layer, this
middleware is a safe no-op — it sets workspace_id = None and all downstream
guards remain in their existing query-param / header driven form.
"""

from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class WorkspaceIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "workspace_id"):
            request.state.workspace_id = user.workspace_id
        else:
            request.state.workspace_id = None
        return await call_next(request)
