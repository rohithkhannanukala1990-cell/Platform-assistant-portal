"""Per-user dismiss/onboarding flags — reuses the existing flat ``UserSetting``
key/value table (already used for global app settings via
``db/repositories/settings.py``) with a ``pref:{username}:{key}`` key prefix,
rather than adding a new table. Scoped single-row queries, not the whole-table
``get_settings()`` read, since this can grow with the number of users.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from ..db.core import engine
from ..db.models.ops import UserSetting


def _full_key(username: str, key: str) -> str:
    return f"pref:{username}:{key}"


def get_pref(username: str, key: str) -> Optional[str]:
    with Session(engine) as session:
        row = session.exec(
            select(UserSetting).where(UserSetting.key == _full_key(username, key))
        ).first()
        return row.value if row else None


def set_pref(username: str, key: str, value: str) -> None:
    full_key = _full_key(username, key)
    with Session(engine) as session:
        row = session.exec(select(UserSetting).where(UserSetting.key == full_key)).first()
        if row:
            row.value = value
            session.add(row)
        else:
            session.add(UserSetting(key=full_key, value=value))
        session.commit()
