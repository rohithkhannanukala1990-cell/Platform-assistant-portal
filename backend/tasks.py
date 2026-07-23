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

from .worker import celery_app
from .database import update_webhook_event

logger = logging.getLogger(__name__)


# ── Async runner ───────────────────────────────────────────────────────────────

def _run_async(coro):
    """
    Run *coro* safely in Celery worker threads (Python 3.10+ compatible).
    asyncio.run() handles loop creation, pending task drain, and cleanup.
    """
    try:
        asyncio.run(coro)
    except RuntimeError:
        # Fallback for environments where a loop already exists (eventlet/gevent pools)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


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
    from .main import _run_triage, _map_to_cloud_event, _route_owner

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
    from .main import _run_triage

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


# ── Task: CI/CD pipeline monitor ───────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.monitor_cicd_pipelines",
    max_retries=1,
    acks_late=True,
)
def monitor_cicd_pipelines(self):
    """
    Simulates a CI/CD pipeline monitoring scan.

    Picks a random failure scenario, creates an Incident, and routes it to
    the owner role that owns that pipeline stage:
      - Security Scan  → NetworkEngineer
      - Test / Build   → Developer
      - Deploy         → Developer
    The incident is then evaluated by the HITL processor.
    """
    import random as _rand
    from .database import save_incident, create_notification
    from .services.demo_fixtures import CICD_MONITOR_SCENARIOS
    from .services.incidents_service import hitl_evaluate as _hitl_evaluate

    logger.info("[celery] monitor_cicd_pipelines: starting scan")

    try:
        scenario = _rand.choice(CICD_MONITOR_SCENARIOS)
        logger.info("[celery] monitor_cicd_pipelines: detected failure stage=%s owner=%s",
                    scenario["stage"], scenario["owner_role"])

        record = save_incident({
            "severity":   scenario["severity"],
            "summary":    scenario["title"],
            "root_cause": f"CI/CD monitor detected a failure in the {scenario['stage']} stage.",
            "action_plan": scenario["action_plan"],
            "commands":   scenario["commands"],
            "evidence":   [f"Pipeline stage: {scenario['stage']}", f"Service: {scenario['service']}"],
            "status":     "OPEN",
            "source":     "cicd-monitor",
            "owner_role": scenario["owner_role"],
        })

        create_notification(
            message=f"🔴 CI/CD Monitor: {scenario['title']}",
            type="critical" if scenario["severity"] in ("High", "Critical") else "warning",
            incident_id=record.id,
        )

        parsed = {
            "summary":     scenario["title"],
            "action_plan": scenario["action_plan"],
            "commands":    scenario["commands"],
        }

        async def _run():
            await _hitl_evaluate(record.id, scenario["severity"], parsed, scenario["owner_role"])

        _run_async(_run())

        logger.info("[celery] monitor_cicd_pipelines: Incident #%s created → %s", record.id, scenario["owner_role"])
        return {"incident_id": record.id, "stage": scenario["stage"], "owner_role": scenario["owner_role"]}

    except Exception as exc:
        logger.error("[celery] monitor_cicd_pipelines failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
