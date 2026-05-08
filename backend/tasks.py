"""
Celery task definitions for AIOps webhook processing.
------------------------------------------------------
Both tasks use a lazy import of ``main`` to avoid a circular-import cycle
(main.py imports tasks.py; tasks.py must not import main at module level).
The lazy import is safe because by the time a task executes, main is already
in sys.modules.

Async coroutines (_run_triage, etc.) are driven via _run_async(), which
creates a fresh event loop, runs the coroutine to completion, and then
drains any asyncio tasks that were spawned internally with create_task()
(e.g. the HITL evaluator).
"""
from __future__ import annotations

import asyncio
import logging

from worker import celery_app
from database import update_webhook_event

logger = logging.getLogger(__name__)


# ── Async runner ───────────────────────────────────────────────────────────────

def _run_async(coro):
    """
    Run *coro* in a brand-new event loop.

    After the coroutine completes, the loop drains any pending tasks that were
    created with asyncio.create_task() during execution (e.g. _hitl_evaluate).
    This is necessary because Celery workers are synchronous threads and have no
    pre-existing event loop.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(coro)
        # Drain background tasks spawned by create_task() (e.g. HITL evaluator)
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ── Task: inbound webhook gateway ──────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.process_inbound_webhook",
    max_retries=3,
    default_retry_delay=30,   # seconds between retries
    acks_late=True,
)
def process_inbound_webhook(self, payload: dict, source: str, event_id: int):
    """
    Celery replacement for the FastAPI BackgroundTask in POST /api/webhooks/inbound.

    Steps:
      1. Normalise the arbitrary inbound payload to a CloudEvent-style log string.
      2. Route to the correct owner role.
      3. Run full AI triage (may trigger HITL or auto-resolve).
      4. Update the WebhookEvent record with the resulting Incident ID.

    Retries up to 3 times with a 30-second delay on transient failures.
    """
    # Lazy import — avoids circular dependency (main imports tasks at module level)
    from main import _run_triage, _map_to_cloud_event, _route_owner

    logger.info("[celery] process_inbound_webhook source=%s event_id=%s", source, event_id)

    try:
        _event_type, log_text, _ = _map_to_cloud_event(payload, source)
        owner_role = _route_owner(source)

        async def _run():
            result = await _run_triage(
                log_text,
                source=f"webhook:{source}",
                owner_role=owner_role,
            )
            update_webhook_event(event_id, status="processed", incident_id=result.get("id"))
            logger.info(
                "[celery] %s → Incident #%s routed to %s",
                source, result.get("id"), owner_role,
            )

        _run_async(_run())

    except Exception as exc:
        update_webhook_event(event_id, status="error")
        logger.error("[celery] Event %s failed: %s", event_id, exc, exc_info=True)
        # Retry on transient errors; propagate on max-retries exceeded
        raise self.retry(exc=exc)


# ── Task: legacy log ingestion webhook ────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.process_webhook_log",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_webhook_log(self, log_text: str, source: str):
    """
    Celery replacement for the FastAPI BackgroundTask in POST /api/webhooks/logs.

    Runs AI triage on a raw log string sent via the simple log-ingestion endpoint.
    Retries up to 3 times on failure.
    """
    from main import _run_triage

    logger.info("[celery] process_webhook_log source=%s", source)

    try:
        async def _run():
            await _run_triage(log_text, source=f"webhook:{source}")

        _run_async(_run())

    except Exception as exc:
        logger.error(
            "[celery] Webhook log triage failed source=%s: %s", source, exc, exc_info=True
        )
        raise self.retry(exc=exc)
