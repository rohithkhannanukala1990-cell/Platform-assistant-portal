"""Webhook delivery-id idempotency (WebhookDelivery ledger)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from ..database import engine
from ..db.models.ops import WebhookDelivery

# Statuses that may be reclaimed so a failed process does not permanently drop the event.
_RECLAIMABLE = frozenset({"error", "failed"})
_DONE = frozenset({"processed", "suppressed", "grouped"})


def extract_delivery_id(
    *,
    source: str,
    headers: dict[str, str],
    body: dict | None = None,
    fallback: str | None = None,
) -> str:
    """Resolve a stable delivery id from provider headers/body, else fallback/uuid."""
    import uuid

    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    body = body if isinstance(body, dict) else {}
    src = (source or "").strip().lower()

    candidates = [
        body.get("delivery_id"),
        h.get("x-github-delivery"),
        h.get("x-gitlab-event-uuid"),
        h.get("x-request-id") if src in {"pagerduty", "datadog"} else None,
        h.get("x-datadog-delivery"),
    ]
    for c in candidates:
        if c is not None and str(c).strip():
            return str(c).strip()
    if fallback and str(fallback).strip():
        return str(fallback).strip()
    return str(uuid.uuid4())


def get_delivery(delivery_id: str) -> WebhookDelivery | None:
    if not (delivery_id or "").strip():
        return None
    with Session(engine) as session:
        return session.get(WebhookDelivery, delivery_id.strip())


def claim_delivery(delivery_id: str, source: str, *, status: str = "received") -> tuple[bool, WebhookDelivery | None]:
    """Insert delivery row after signature verify.

    Returns (is_new, row). is_new=False means duplicate — caller should return 200.
    Rows previously marked ``error``/``failed`` are reclaimed so provider retries
    are not permanently dropped.
    """
    did = (delivery_id or "").strip()
    if not did:
        return True, None
    row = WebhookDelivery(
        delivery_id=did,
        source=(source or "").strip().lower() or "unknown",
        received_at=datetime.now(timezone.utc),
        status=status,
    )
    try:
        with Session(engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return True, row
    except IntegrityError:
        with Session(engine) as session:
            existing = session.get(WebhookDelivery, did)
            if existing is None:
                return False, None
            if existing.status in _RECLAIMABLE:
                existing.status = status
                existing.source = (source or "").strip().lower() or existing.source
                session.add(existing)
                session.commit()
                session.refresh(existing)
                return True, existing
            return False, existing


def mark_delivery_status(delivery_id: str, status: str) -> None:
    did = (delivery_id or "").strip()
    if not did:
        return
    with Session(engine) as session:
        row = session.get(WebhookDelivery, did)
        if not row:
            return
        row.status = status
        session.add(row)
        session.commit()


def delivery_already_processed(delivery_id: str | None) -> bool:
    """True when delivery ledger shows a successful terminal status."""
    if not delivery_id:
        return False
    row = get_delivery(delivery_id)
    return row is not None and row.status in _DONE
