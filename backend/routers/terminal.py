"""REST surface for the in-app terminal — capability discovery and history
recovery. Command execution itself stays on the ``/ws/terminal`` WebSocket
(see ``backend/ws_portal.py``); these are read-only companions to it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import User, get_current_user
from ..services.isolation import require_tenant

router = APIRouter(prefix="/api/terminal", tags=["terminal"])


@router.get("/capabilities")
def get_terminal_capabilities(current_user: User = Depends(get_current_user)):
    from ..services.terminal_capabilities import get_capabilities

    return list(get_capabilities().values())


@router.get("/history")
def get_terminal_history(
    request: Request,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
):
    from ..services.terminal_service import load_history

    tenant_id = require_tenant(request)
    return {
        "history": load_history(
            tenant_id=tenant_id, username=current_user.username, limit=min(max(limit, 1), 100)
        )
    }
