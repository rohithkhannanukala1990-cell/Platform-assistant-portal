"""Server-side JWT session registry + revoke denylist (jti)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, select

from ..database import engine


class AuthSession(SQLModel, table=True):
    """Tracks issued JWTs by jti for list/revoke. Revoked sessions reject auth."""

    __tablename__ = "auth_session"

    id: Optional[int] = Field(default=None, primary_key=True)
    jti: str = Field(index=True, unique=True)
    user_id: int = Field(index=True)
    username: str = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime
    revoked_at: Optional[datetime] = Field(default=None, index=True)
    ip_address: str = Field(default="")
    user_agent: str = Field(default="")


def register_session(
    *,
    jti: str,
    username: str,
    user_id: int,
    expires_at: datetime,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    with Session(engine) as session:
        session.add(
            AuthSession(
                jti=jti,
                username=username,
                user_id=user_id,
                expires_at=expires_at,
                ip_address=ip_address or "",
                user_agent=(user_agent or "")[:512],
            )
        )
        session.commit()


def is_jti_revoked(jti: str | None) -> bool:
    """Return True only when a session row exists and is revoked.

    Tokens without jti (legacy) and unknown jti values are allowed so that
    short-TTL JWTs remain usable if the registry row is missing.
    """
    if not jti:
        return False
    with Session(engine) as session:
        row = session.exec(select(AuthSession).where(AuthSession.jti == jti)).first()
        if row is None:
            return False
        return row.revoked_at is not None


def revoke_jti(jti: str) -> bool:
    """Revoke a session by jti. Returns True if a row was updated."""
    if not jti:
        return False
    with Session(engine) as session:
        row = session.exec(select(AuthSession).where(AuthSession.jti == jti)).first()
        if not row:
            return False
        if row.revoked_at is None:
            row.revoked_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
        return True


def list_sessions_for_user(username: str, *, include_revoked: bool = False) -> list[dict]:
    with Session(engine) as session:
        q = select(AuthSession).where(AuthSession.username == username)
        if not include_revoked:
            q = q.where(AuthSession.revoked_at.is_(None))  # type: ignore[attr-defined]
        rows = session.exec(q.order_by(AuthSession.created_at.desc())).all()
    now = datetime.now(timezone.utc)
    out: list[dict] = []
    for r in rows:
        expired = bool(r.expires_at and r.expires_at.replace(tzinfo=timezone.utc) < now)
        out.append(
            {
                "id": r.id,
                "jti": r.jti,
                "username": r.username,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                "ip_address": r.ip_address,
                "user_agent": r.user_agent,
                "active": r.revoked_at is None and not expired,
            }
        )
    return out


def revoke_all_for_user(username: str) -> int:
    count = 0
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        rows = session.exec(
            select(AuthSession).where(
                AuthSession.username == username,
                AuthSession.revoked_at.is_(None),  # type: ignore[attr-defined]
            )
        ).all()
        for r in rows:
            r.revoked_at = now
            session.add(r)
            count += 1
        session.commit()
    return count
