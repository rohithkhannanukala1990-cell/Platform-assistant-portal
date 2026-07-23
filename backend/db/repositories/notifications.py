"""Notification create / list / mark-read helpers."""
from __future__ import annotations

from sqlmodel import Session, select

from ..core import engine
from ..models.ops import Notification


def create_notification(
    message: str, type: str = "info", incident_id: int | None = None
) -> Notification:
    n = Notification(message=message, type=type, incident_id=incident_id)
    with Session(engine) as session:
        session.add(n)
        session.commit()
        session.refresh(n)
    return n


def list_notifications(limit: int = 200) -> list[dict]:
    limit = max(1, min(int(limit or 200), 500))
    with Session(engine) as session:
        rows = session.exec(
            select(Notification).order_by(Notification.timestamp.desc()).limit(limit)
        ).all()
    return [_serialize_notification(r) for r in rows]


def get_all_notifications() -> list[dict]:
    return list_notifications(limit=200)


def mark_notification_read(notification_id: int) -> dict | None:
    with Session(engine) as session:
        row = session.get(Notification, notification_id)
        if not row:
            return None
        row.is_read = True
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialize_notification(row)


def _serialize_notification(n: Notification) -> dict:
    return {
        "id": n.id,
        "timestamp": n.timestamp.isoformat(),
        "message": n.message,
        "type": n.type,
        "is_read": n.is_read,
        "incident_id": n.incident_id,
    }


serialize_notification = _serialize_notification

__all__ = [
    "create_notification",
    "list_notifications",
    "get_all_notifications",
    "mark_notification_read",
    "_serialize_notification",
    "serialize_notification",
]
