"""RBAC dependency: `Depends(require_permission(\"resource\", \"action\"))`."""

from __future__ import annotations

from fastapi import HTTPException, Request
from sqlmodel import Session

from ..database import engine
from ..rbac_core import check_user_permission


def require_permission(resource: str, action: str):
    """
    FastAPI dependency factory.
    Reads `X-User-Id` from the request. Skips enforcement when value is `admin` (dev escape hatch).
    """

    def _dep(request: Request) -> None:
        uid = (request.headers.get("X-User-Id") or "").strip()
        if uid == "admin":
            return
        if not uid:
            raise HTTPException(status_code=403, detail="Missing X-User-Id header")
        with Session(engine) as session:
            allowed, reason = check_user_permission(
                session,
                uid,
                resource,
                action,
                "global",
                "",
            )
            if not allowed:
                raise HTTPException(status_code=403, detail=reason or "Forbidden")

    return _dep
