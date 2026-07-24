"""Session list / revoke / logout under /api/auth."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import (
    User,
    get_current_user,
    normalize_role,
    peek_token_claims,
    write_audit,
)
from ..database import engine
from ..services.auth_sessions import AuthSession, list_sessions_for_user, revoke_all_for_user, revoke_jti

router = APIRouter(prefix="/api/auth", tags=["auth-sessions"])


class RevokeSessionBody(BaseModel):
    jti: str | None = None
    username: str | None = None
    revoke_all: bool = False


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


@router.get("/sessions")
def get_sessions(
    username: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """List active sessions for the current user (admin may query another username)."""
    target = current_user.username
    if username and username != current_user.username:
        if normalize_role(current_user.role) != "Admin":
            raise HTTPException(status_code=403, detail="Forbidden")
        target = username
    return {"sessions": list_sessions_for_user(target, include_revoked=False)}


@router.post("/sessions/revoke")
def revoke_session(
    body: RevokeSessionBody,
    current_user: User = Depends(get_current_user),
):
    """Revoke a session by jti. Admins may revoke another user's sessions."""
    if body.revoke_all and body.username:
        if normalize_role(current_user.role) != "Admin":
            raise HTTPException(status_code=403, detail="Forbidden")
        n = revoke_all_for_user(body.username)
        write_audit(
            actor=current_user.username,
            actor_role=normalize_role(current_user.role),
            event_type="session_revoke",
            resource=f"user:{body.username}",
            detail=f"revoked_all count={n}",
        )
        return {"ok": True, "revoked": n}

    jti = (body.jti or "").strip()
    if not jti:
        raise HTTPException(status_code=400, detail="jti is required")

    with Session(engine) as session:
        row = session.exec(select(AuthSession).where(AuthSession.jti == jti)).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if row.username != current_user.username and normalize_role(current_user.role) != "Admin":
            raise HTTPException(status_code=404, detail="Session not found")

    ok = revoke_jti(jti)
    write_audit(
        actor=current_user.username,
        actor_role=normalize_role(current_user.role),
        event_type="session_revoke",
        resource="auth",
        detail=f"jti={jti[:8]}",
    )
    return {"ok": bool(ok), "jti": jti}


@router.post("/logout")
def api_logout(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Revoke the current JWT session and audit logout."""
    token = _bearer_token(request)
    jti = None
    if token:
        claims = peek_token_claims(token)
        jti = claims.get("jti")
    if jti:
        revoke_jti(str(jti))
    write_audit(
        actor=current_user.username,
        actor_role=normalize_role(current_user.role),
        event_type="logout",
        resource="auth",
        detail="session revoked" if jti else "logout without jti",
        ip_address=(request.client.host if request.client else ""),
    )
    return {"ok": True}
