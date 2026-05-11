"""Persist health alerts, optional Slack webhook, optional in-app broadcast hook."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import httpx
from sqlmodel import Session

from .database import HealthAlert, engine

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL", "").strip()


def _persist_alert(
    alert_id: str,
    user_id: str,
    message: str,
    severity: str,
    created_at: datetime,
) -> None:
    row = HealthAlert(
        id=alert_id,
        user_id=user_id or "",
        message=message,
        severity=severity,
        status="active",
        created_at=created_at,
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()


async def send_alert(
    user_id: str,
    message: str,
    severity: str = "info",
) -> None:
    alert_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc)
    await asyncio.to_thread(
        _persist_alert, alert_id, user_id, message, severity, created_at
    )

    try:
        from . import connection_manager as cm  # type: ignore[attr-defined]

        broadcast = getattr(cm, "broadcast_to_user", None)
        if callable(broadcast):
            await broadcast(
                user_id,
                "health_alert",
                {
                    "id": alert_id,
                    "message": message,
                    "severity": severity,
                    "timestamp": created_at.isoformat(),
                },
            )
    except ImportError:
        pass

    if SLACK_WEBHOOK and severity in ("warning", "critical"):
        emoji = "⚠️" if severity == "warning" else "🚨"
        async with httpx.AsyncClient(timeout=15.0) as client:
            await client.post(
                SLACK_WEBHOOK,
                json={"text": f"{emoji} *Portal Health Alert*\n{message}"},
            )
