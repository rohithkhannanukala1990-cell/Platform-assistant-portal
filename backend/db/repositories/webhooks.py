"""Webhook event persistence helpers."""
from __future__ import annotations

from sqlmodel import Session, select

from ..core import engine
from ..models.ops import WebhookEvent


def save_webhook_event(data: dict) -> WebhookEvent:
    ev = WebhookEvent(
        source=data["source"],
        event_type=data.get("event_type", ""),
        owner_role=data.get("owner_role", "Admin"),
        status=data.get("status", "accepted"),
        incident_id=data.get("incident_id"),
        raw_payload=data.get("raw_payload", "{}"),
        cloud_event_id=data.get("cloud_event_id", ""),
    )
    with Session(engine) as session:
        session.add(ev)
        session.commit()
        session.refresh(ev)
    return ev


def update_webhook_event(event_id: int, status: str, incident_id: int | None = None):
    with Session(engine) as session:
        ev = session.get(WebhookEvent, event_id)
        if ev:
            ev.status = status
            if incident_id is not None:
                ev.incident_id = incident_id
            session.add(ev)
            session.commit()


def get_webhook_event(event_id: int) -> WebhookEvent | None:
    with Session(engine) as session:
        ev = session.get(WebhookEvent, event_id)
        if ev is None:
            return None
        session.expunge(ev)
        return ev


def get_recent_webhook_events(limit: int = 40) -> list[dict]:
    limit = max(1, min(int(limit or 40), 100))
    with Session(engine) as session:
        rows = session.exec(
            select(WebhookEvent).order_by(WebhookEvent.timestamp.desc()).limit(limit)
        ).all()
    return [_serialize_webhook_event(r) for r in rows]


def _serialize_webhook_event(e: WebhookEvent) -> dict:
    return {
        "id": e.id,
        "timestamp": e.timestamp.isoformat(),
        "source": e.source,
        "event_type": e.event_type,
        "owner_role": e.owner_role,
        "status": e.status,
        "incident_id": e.incident_id,
        "cloud_event_id": e.cloud_event_id,
    }


serialize_webhook_event = _serialize_webhook_event

__all__ = [
    "save_webhook_event",
    "update_webhook_event",
    "get_recent_webhook_events",
    "_serialize_webhook_event",
    "serialize_webhook_event",
]
