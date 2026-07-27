"""Scheduled health checks, auto-heal, and log retention (APScheduler)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, delete

from .auto_heal import auto_healer
from .database import HealthAlert, engine
from .health import health_checker
from .observability.logger import logger

scheduler = AsyncIOScheduler(timezone=timezone.utc)
_started = False


async def run_health_checks() -> None:
    logger.info("Running scheduled health checks (tools + performance)")
    await health_checker.check_tool_connections()
    await health_checker.check_slow_queries()


async def run_expiry_checks() -> None:
    logger.info("Running scheduled credential expiry checks")
    await health_checker.check_tool_connections()


async def run_auto_heal() -> None:
    logger.info("Running scheduled auto-heal")
    results = await auto_healer.heal_all_low_risk()
    logger.info("Auto-heal batch finished", extra={"actions": len(results)})


def archive_old_logs() -> None:
    """Prune old audit logs (retention setting) and resolved health alerts."""
    from .services.audit_compliance import get_audit_retention_days, prune_audit_logs

    now = datetime.now(timezone.utc)
    retention_days = get_audit_retention_days()
    cut_alerts = now - timedelta(days=30)
    deleted = prune_audit_logs(retention_days=retention_days)
    with Session(engine) as session:
        session.exec(
            delete(HealthAlert).where(
                HealthAlert.status == "resolved",
                HealthAlert.created_at < cut_alerts,
            )
        )
        session.commit()
    logger.info(
        "Archived old logs",
        extra={
            "audit_retention_days": retention_days,
            "audit_deleted": deleted,
            "alerts_cutoff": cut_alerts.isoformat(),
        },
    )


def _archive_job() -> None:
    try:
        archive_old_logs()
    except Exception as exc:
        logger.warning("archive_old_logs failed", extra={"error": str(exc)})


def start_scheduler() -> None:
    global _started
    if os.getenv("SKIP_BACKGROUND_SCHEDULER", "").lower() in ("1", "true", "yes"):
        logger.info("Background scheduler disabled (SKIP_BACKGROUND_SCHEDULER)")
        return
    if _started:
        return
    scheduler.add_job(
        run_health_checks,
        "interval",
        hours=6,
        id="health_checks",
        replace_existing=True,
    )
    scheduler.add_job(
        run_expiry_checks,
        "interval",
        hours=24,
        id="expiry_checks",
        replace_existing=True,
    )
    scheduler.add_job(
        run_auto_heal,
        "interval",
        hours=12,
        id="auto_heal",
        replace_existing=True,
    )
    scheduler.add_job(
        _archive_job,
        "interval",
        days=30,
        id="archive_logs",
        replace_existing=True,
    )
    scheduler.start()
    _started = True
    logger.info("APScheduler started (health, expiry, auto-heal, archive)")


def shutdown_scheduler() -> None:
    global _started
    if not _started:
        return
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
    except Exception as exc:
        logger.warning("Scheduler shutdown error", extra={"error": str(exc)})
    finally:
        _started = False
        logger.info("APScheduler stopped")
