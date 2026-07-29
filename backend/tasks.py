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
import json
import logging

from celery.exceptions import MaxRetriesExceededError

from .worker import celery_app
from .database import update_webhook_event
from .observability.metrics import record_celery_task_failure, record_celery_task_retry
from .services.celery_failures import record_task_failure

logger = logging.getLogger(__name__)

_TRIAGE_MAX_RETRIES = 5

# Permanent client/data errors — do not burn retries (ID-046).
_PERMANENT_ERRORS = (ValueError, KeyError, TypeError, json.JSONDecodeError)


def _run_async(coro):
    """
    Run *coro* safely in Celery worker threads (Python 3.10+ compatible).
    asyncio.run() handles loop creation, pending task drain, and cleanup.
    """
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _backoff_countdown(retries: int) -> int:
    """Exponential backoff with cap (seconds): 5, 10, 20, 40, 80… max 300."""
    return min(300, 5 * (2 ** max(0, int(retries))))


def _is_permanent(exc: BaseException) -> bool:
    if isinstance(exc, _PERMANENT_ERRORS):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, _PERMANENT_ERRORS)


def _dead_letter(task_self, *, queue: str, args, error: BaseException) -> None:
    name = getattr(task_self, "name", "") or task_self.__name__
    retries = int(getattr(task_self.request, "retries", 0) or 0)
    task_id = str(getattr(task_self.request, "id", "") or "")
    try:
        record_task_failure(
            task_name=name,
            task_id=task_id,
            queue=queue,
            args=list(args) if args is not None else [],
            kwargs={},
            error=str(error),
            retries=retries,
        )
    except Exception as persist_exc:
        logger.error("[celery] failed to persist dead-letter: %s", persist_exc)
    try:
        record_celery_task_failure(name, queue)
    except Exception:
        pass
    logger.error(
        "[celery] dead-letter task=%s queue=%s retries=%s error=%s",
        name,
        queue,
        retries,
        error,
        exc_info=True,
    )


@celery_app.task(
    bind=True,
    name="tasks.process_inbound_webhook",
    max_retries=_TRIAGE_MAX_RETRIES,
    acks_late=True,
    queue="triage",
)
def process_inbound_webhook(
    self, payload: dict, source: str, event_id: int, delivery_id: str | None = None
):
    """Normalize inbound payload → rules-based correlation → AI triage.

    ``delivery_id`` is the idempotency key: already-processed deliveries skip
    re-ingest so Celery retries do not create duplicate incidents (ID-034).
    """
    from .main import _map_to_cloud_event, _route_owner
    from .services.incidents_service import ingest_webhook_alert
    from .services.webhook_delivery import delivery_already_processed, mark_delivery_status
    from .db.repositories.webhooks import get_webhook_event

    logger.info(
        "[celery] process_inbound_webhook source=%s event_id=%s delivery_id=%s",
        source,
        event_id,
        delivery_id,
    )

    try:
        # Idempotency: skip if delivery or webhook event already succeeded.
        if delivery_id and delivery_already_processed(delivery_id):
            logger.info(
                "[celery] process_inbound_webhook skip already-processed delivery_id=%s",
                delivery_id,
            )
            return {"skipped": True, "reason": "delivery_already_processed", "delivery_id": delivery_id}

        existing_ev = get_webhook_event(event_id)
        if existing_ev and existing_ev.status in {"processed", "suppressed", "grouped"} and existing_ev.incident_id:
            if delivery_id:
                mark_delivery_status(delivery_id, existing_ev.status)
            return {
                "skipped": True,
                "reason": "event_already_processed",
                "incident_id": existing_ev.incident_id,
            }

        _event_type, log_text, _ = _map_to_cloud_event(payload, source)
        owner_role = _route_owner(source)
        tenant_id = str(payload.get("tenant_id") or "default")

        async def _run():
            result = await ingest_webhook_alert(
                log_text,
                source=f"webhook:{source}",
                owner_role=owner_role,
                tenant_id=tenant_id,
                payload=payload,
            )
            status = result.get("status") or "processed"
            if status in ("suppressed", "grouped"):
                update_webhook_event(event_id, status=status, incident_id=result.get("id"))
            else:
                update_webhook_event(event_id, status="processed", incident_id=result.get("id"))
            if delivery_id:
                mark_delivery_status(delivery_id, status if status in ("suppressed", "grouped") else "processed")
            logger.info(
                "[celery] %s → %s incident=%s routed to %s",
                source,
                status,
                result.get("id"),
                owner_role,
            )

        _run_async(_run())

    except Exception as exc:
        update_webhook_event(event_id, status="error")
        if delivery_id:
            try:
                mark_delivery_status(delivery_id, "error")
            except Exception:
                pass
        if _is_permanent(exc):
            _dead_letter(
                self,
                queue="triage",
                args=[payload, source, event_id, delivery_id],
                error=exc,
            )
            raise
        retries = int(getattr(self.request, "retries", 0) or 0)
        try:
            record_celery_task_retry("tasks.process_inbound_webhook", "triage")
        except Exception:
            pass
        try:
            raise self.retry(exc=exc, countdown=_backoff_countdown(retries))
        except MaxRetriesExceededError:
            _dead_letter(
                self,
                queue="triage",
                args=[payload, source, event_id, delivery_id],
                error=exc,
            )
            raise


@celery_app.task(
    bind=True,
    name="tasks.process_webhook_log",
    max_retries=_TRIAGE_MAX_RETRIES,
    acks_late=True,
    queue="triage",
)
def process_webhook_log(self, log_text: str, source: str):
    """Rules-based correlation + AI triage on raw log string."""
    from .services.incidents_service import ingest_webhook_alert

    logger.info("[celery] process_webhook_log source=%s", source)

    try:
        async def _run():
            await ingest_webhook_alert(log_text, source=f"webhook:{source}")

        _run_async(_run())

    except Exception as exc:
        if _is_permanent(exc):
            _dead_letter(
                self,
                queue="triage",
                args=[log_text, source],
                error=exc,
            )
            raise
        retries = int(getattr(self.request, "retries", 0) or 0)
        try:
            record_celery_task_retry("tasks.process_webhook_log", "triage")
        except Exception:
            pass
        logger.error(
            "[celery] Webhook log triage failed source=%s: %s", source, exc, exc_info=True
        )
        try:
            raise self.retry(exc=exc, countdown=_backoff_countdown(retries))
        except MaxRetriesExceededError:
            _dead_letter(
                self,
                queue="triage",
                args=[log_text, source],
                error=exc,
            )
            raise


@celery_app.task(
    bind=True,
    name="tasks.notify_incident",
    max_retries=3,
    acks_late=True,
    queue="notify",
)
def notify_incident(self, incident_id: int, message: str, ntype: str = "info"):
    """Durable notification create (notify queue)."""
    from .database import create_notification

    try:
        create_notification(message=message, type=ntype, incident_id=incident_id)
    except Exception as exc:
        if _is_permanent(exc):
            _dead_letter(
                self,
                queue="notify",
                args=[incident_id, message, ntype],
                error=exc,
            )
            raise
        retries = int(getattr(self.request, "retries", 0) or 0)
        try:
            record_celery_task_retry("tasks.notify_incident", "notify")
        except Exception:
            pass
        try:
            raise self.retry(exc=exc, countdown=_backoff_countdown(retries))
        except MaxRetriesExceededError:
            _dead_letter(
                self,
                queue="notify",
                args=[incident_id, message, ntype],
                error=exc,
            )
            raise


@celery_app.task(
    bind=True,
    name="tasks.monitor_cicd_pipelines",
    max_retries=1,
    acks_late=True,
    queue="celery",
)
def monitor_cicd_pipelines(self):
    """
    Simulates a CI/CD pipeline monitoring scan.

    Picks a random failure scenario, creates an Incident, and routes it to
    the owner role that owns that pipeline stage.
    """
    import random as _rand
    from .database import save_incident, create_notification
    from .services.demo_fixtures import CICD_MONITOR_SCENARIOS, demo_data_enabled
    from .services.incidents_service import hitl_evaluate as _hitl_evaluate

    if not demo_data_enabled():
        logger.info(
            "[celery] monitor_cicd_pipelines: skipped (ENABLE_DEMO_DATA=false; no fake incidents)"
        )
        return {"skipped": True, "reason": "demo_data_disabled"}

    logger.info("[celery] monitor_cicd_pipelines: starting scan")

    try:
        scenario = _rand.choice(CICD_MONITOR_SCENARIOS)
        logger.info(
            "[celery] monitor_cicd_pipelines: detected failure stage=%s owner=%s",
            scenario["stage"],
            scenario["owner_role"],
        )

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

        logger.info(
            "[celery] monitor_cicd_pipelines: Incident #%s created → %s",
            record.id,
            scenario["owner_role"],
        )
        return {
            "incident_id": record.id,
            "stage": scenario["stage"],
            "owner_role": scenario["owner_role"],
        }

    except Exception as exc:
        retries = int(getattr(self.request, "retries", 0) or 0)
        try:
            record_celery_task_retry("tasks.monitor_cicd_pipelines", "celery")
        except Exception:
            pass
        try:
            raise self.retry(exc=exc, countdown=_backoff_countdown(retries))
        except MaxRetriesExceededError:
            _dead_letter(self, queue="celery", args=[], error=exc)
            raise
