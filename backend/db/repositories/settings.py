"""User settings get / update helpers."""
from __future__ import annotations

from sqlmodel import Session, select

from ..core import engine
from ..models.ops import UserSetting


def get_settings() -> dict:
    with Session(engine) as session:
        rows = session.exec(select(UserSetting)).all()
    return {r.key: r.value for r in rows}


def update_settings(updates: dict) -> dict:
    with Session(engine) as session:
        for key, value in updates.items():
            row = session.exec(select(UserSetting).where(UserSetting.key == key)).first()
            if row:
                row.value = str(value)
                session.add(row)
            else:
                session.add(UserSetting(key=key, value=str(value)))
        session.commit()
    return get_settings()


__all__ = ["get_settings", "update_settings"]
