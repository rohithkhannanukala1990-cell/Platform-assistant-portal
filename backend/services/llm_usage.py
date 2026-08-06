"""Persist LLM token usage events and bump provider monthly counters."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

logger = logging.getLogger(__name__)


def record_llm_usage(
    *,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
    config_id: Optional[int] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    source: str = "unknown",
    latency_ms: Optional[int] = None,
    request_id: Optional[str] = None,
) -> None:
    """Best-effort write — never fail the LLM call if metering fails."""
    try:
        from ..auth import LLMProviderConfig, engine
        from ..db.models.ai_models import LLMUsageEvent

        prompt_tokens = max(0, int(prompt_tokens or 0))
        completion_tokens = max(0, int(completion_tokens or 0))
        total = max(0, int(total_tokens or 0)) or (prompt_tokens + completion_tokens)

        with Session(engine) as session:
            session.add(
                LLMUsageEvent(
                    id=str(uuid.uuid4()),
                    created_at=datetime.now(timezone.utc),
                    tenant_id=(tenant_id or "default").strip() or "default",
                    workspace_id=(workspace_id or None),
                    user_id=(user_id or None),
                    source=(source or "unknown").strip() or "unknown",
                    provider=(provider or "").strip().lower(),
                    model=(model or "").strip(),
                    config_id=config_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total,
                    estimated_cost_usd=float(estimated_cost_usd or 0.0),
                    latency_ms=latency_ms,
                    request_id=request_id,
                )
            )
            if config_id is not None and total:
                row = session.get(LLMProviderConfig, config_id)
                if row is not None:
                    row.tokens_used_this_month = int(row.tokens_used_this_month or 0) + total
                    row.updated_at = datetime.now(timezone.utc)
                    session.add(row)
            session.commit()
    except Exception:
        logger.warning("Failed to record LLM usage event", exc_info=True)
