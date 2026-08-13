"""RBAC dependency: `Depends(require_permission(\"resource\", \"action\"))`."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from ..auth import User, get_current_user
from ..database import engine
from ..rbac_core import check_user_permission


def require_permission(resource: str, action: str):
    """FastAPI dependency factory backed only by authenticated identity."""

    def _dep(
        request: Request,
        _authenticated_user: User = Depends(get_current_user),
    ) -> None:
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="Unauthenticated")
        with Session(engine) as session:
            allowed, reason = check_user_permission(
                session,
                user.id,
                resource,
                action,
                "global",
                "",
            )
            if not allowed:
                raise HTTPException(status_code=403, detail=reason or "Forbidden")

    return _dep
