"""Persist Celery task failures for manual replay (dead-letter pattern)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from ..database import engine
from ..db.models.ops import CeleryTaskFailure


def record_task_failure(
    *,
    task_name: str,
    task_id: str = "",
    queue: str = "celery",
    args: list | tuple | None = None,
    kwargs: dict | None = None,
    error: str = "",
    retries: int = 0,
) -> CeleryTaskFailure:
    row = CeleryTaskFailure(
        task_name=task_name or "",
        task_id=task_id or "",
        queue=queue or "celery",
        args_json=json.dumps(list(args or []), default=str)[:20000],
        kwargs_json=json.dumps(dict(kwargs or {}), default=str)[:20000],
        error=(error or "")[:8000],
        retries=int(retries or 0),
        failed_at=datetime.now(timezone.utc),
    )
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def mark_failure_replayed(failure_id: int) -> None:
    with Session(engine) as session:
        row = session.get(CeleryTaskFailure, failure_id)
        if not row:
            return
        row.replayed_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
