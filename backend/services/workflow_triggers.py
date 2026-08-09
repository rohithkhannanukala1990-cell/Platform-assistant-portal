"""Scheduled and event-driven workflow triggers.

Uses the existing APScheduler instance (cron_jobs.scheduler) — never a second scheduler.
Redis/in-process fallback mirrors terminal_service for kill-switch override and queues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..auth import write_audit
from ..db.core import engine
from ..db.models.workflows import WorkflowDefinition, WorkflowRun

logger = logging.getLogger(__name__)

JOB_PREFIX = "workflow_sched_"
MAX_TRIGGER_DEPTH = 3
EVENT_SOURCES = (
    "alert_rule_match",
    "webhook_inbound",
    "catalog_entity_changed",
    "agent_run_completed",
    "incident_created",
)

_kill_override: bool | None = None
_kill_lock = threading.Lock()
_queued_runs: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
_queue_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_json(raw: str | None, default: Any) -> Any:
    try:
        data = json.loads(raw or "")
        return data if data is not None else default
    except (json.JSONDecodeError, TypeError, ValueError):
        return default


def _redis():
    try:
        from .redis_url import redis_url
        import redis as redis_sync

        url = redis_url()
        if not url:
            return None
        client = redis_sync.Redis.from_url(
            url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True
        )
        client.ping()
        return client
    except Exception:
        return None


def triggers_enabled() -> bool:
    """Kill switch: runtime override > env WORKFLOWS_TRIGGERS_ENABLED (default true)."""
    with _kill_lock:
        if _kill_override is not None:
            return bool(_kill_override)
    client = _redis()
    if client is not None:
        try:
            raw = client.get("workflows:triggers_enabled")
            if raw is not None:
                return str(raw).strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            pass
    env = (os.environ.get("WORKFLOWS_TRIGGERS_ENABLED") or "true").strip().lower()
    return env in {"1", "true", "yes", "on", ""}


def set_triggers_enabled(enabled: bool, *, actor: str = "admin") -> bool:
    global _kill_override
    with _kill_lock:
        _kill_override = bool(enabled)
    client = _redis()
    if client is not None:
        try:
            client.set("workflows:triggers_enabled", "true" if enabled else "false")
        except Exception:
            pass
    write_audit(
        actor=actor,
        actor_role="Admin",
        event_type="workflow_triggers_kill_switch",
        resource="workflows:triggers",
        detail=f"enabled={enabled}",
    )
    return triggers_enabled()


def _audit_suppressed(
    *,
    workflow_id: str,
    tenant_id: str,
    reason: str,
    actor: str = "system",
) -> None:
    write_audit(
        actor=actor,
        actor_role="system",
        event_type="workflow_trigger_suppressed",
        resource=f"workflow:{workflow_id}",
        detail=f"tenant_id={tenant_id}; {reason}"[:800],
    )


def match_event_config(config: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Evaluate event trigger_config against payload. Tenant filtering is separate."""
    if not isinstance(config, dict) or not isinstance(payload, dict):
        return False
    cfg_source = str(config.get("source") or "").strip()
    if not cfg_source:
        return False
    if str(payload.get("source") or "").strip() != cfg_source:
        return False

    for key, expected in config.items():
        if key == "source":
            continue
        if key.endswith("_pattern"):
            field = key[: -len("_pattern")]
            if field not in payload:
                return False
            try:
                if not re.search(str(expected), str(payload.get(field) or "")):
                    return False
            except re.error:
                return False
            continue
        if key not in payload:
            return False
        actual = payload.get(key)
        if isinstance(expected, list):
            if actual not in expected and str(actual) not in {str(x) for x in expected}:
                return False
        else:
            if actual != expected and str(actual) != str(expected):
                return False
    return True


def _count_runs_last_hour(session: Session, workflow_id: str, tenant_id: str) -> int:
    hour_ago = _now() - timedelta(hours=1)
    rows = session.exec(
        select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.tenant_id == tenant_id,
            WorkflowRun.started_at >= hour_ago,
        )
    ).all()
    return len(rows)


def _count_active_runs(session: Session, workflow_id: str, tenant_id: str) -> int:
    rows = session.exec(
        select(WorkflowRun).where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.tenant_id == tenant_id,
            col(WorkflowRun.status).in_(["pending", "running", "pending_approval"]),
        )
    ).all()
    return len(rows)


async def _start_automatic_run(
    wf: WorkflowDefinition,
    *,
    triggered_by: str,
    payload: dict[str, Any],
    trigger_depth: int = 0,
) -> Optional[str]:
    """Apply guardrails then start_workflow. Returns run id or None if suppressed."""
    from .workflow_engine import start_workflow

    if not triggers_enabled():
        _audit_suppressed(
            workflow_id=wf.id,
            tenant_id=wf.tenant_id,
            reason="kill_switch WORKFLOWS_TRIGGERS_ENABLED=false",
            actor=triggered_by,
        )
        return None

    if trigger_depth > MAX_TRIGGER_DEPTH:
        _audit_suppressed(
            workflow_id=wf.id,
            tenant_id=wf.tenant_id,
            reason=f"trigger_depth={trigger_depth} exceeds max {MAX_TRIGGER_DEPTH}",
            actor=triggered_by,
        )
        return None

    with Session(engine) as session:
        # Re-load fresh caps
        row = session.get(WorkflowDefinition, wf.id)
        if not row or not row.enabled:
            return None
        session.expunge(row)

    with Session(engine) as session:
        recent = _count_runs_last_hour(session, row.id, row.tenant_id)
        if recent >= int(row.max_runs_per_hour or 12):
            _audit_suppressed(
                workflow_id=row.id,
                tenant_id=row.tenant_id,
                reason=f"max_runs_per_hour={row.max_runs_per_hour} exceeded (count={recent})",
                actor=triggered_by,
            )
            return None
        active = _count_active_runs(session, row.id, row.tenant_id)
        if active >= int(row.max_concurrent_runs or 1):
            mode = (row.on_concurrent_limit or "drop").strip().lower()
            if mode == "queue":
                with _queue_lock:
                    _queued_runs[row.id].append(
                        {
                            "tenant_id": row.tenant_id,
                            "triggered_by": triggered_by,
                            "payload": dict(payload),
                            "trigger_depth": trigger_depth,
                        }
                    )
                _audit_suppressed(
                    workflow_id=row.id,
                    tenant_id=row.tenant_id,
                    reason=f"max_concurrent_runs={row.max_concurrent_runs} — queued",
                    actor=triggered_by,
                )
                return None
            _audit_suppressed(
                workflow_id=row.id,
                tenant_id=row.tenant_id,
                reason=f"max_concurrent_runs={row.max_concurrent_runs} — dropped",
                actor=triggered_by,
            )
            return None

    force_dry = row.first_live_run_approved_at is None
    initial = dict(payload)
    initial["trigger_depth"] = trigger_depth
    if force_dry:
        initial["_forced_first_dry_run"] = True

    try:
        run = await start_workflow(
            row.id,
            row.tenant_id,
            triggered_by=triggered_by,
            initial_context=initial,
            dry_run=force_dry,
            automatic=True,
        )
        return run.id
    except Exception as exc:
        logger.warning(
            "automatic workflow start failed workflow_id=%s error=%s",
            row.id,
            exc,
        )
        _audit_suppressed(
            workflow_id=row.id,
            tenant_id=row.tenant_id,
            reason=f"start_failed: {exc}",
            actor=triggered_by,
        )
        return None


async def fire_event(
    source: str,
    payload: dict,
    tenant_id: str,
    *,
    parent_trigger_depth: int | None = None,
) -> list[str]:
    """Start matching event workflows. Never raises to the caller."""
    started: list[str] = []
    try:
        if not triggers_enabled():
            return started
        src = (source or "").strip()
        if not src:
            return started
        body = dict(payload or {})
        body.setdefault("source", src)
        if parent_trigger_depth is None:
            depth = 0
        else:
            depth = int(parent_trigger_depth) + 1

        with Session(engine) as session:
            rows = session.exec(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.tenant_id == tenant_id,
                    WorkflowDefinition.enabled == True,  # noqa: E712
                    WorkflowDefinition.trigger_type == "event",
                )
            ).all()
            defs = []
            for r in rows:
                session.expunge(r)
                defs.append(r)

        for wf in defs:
            cfg = _parse_json(wf.trigger_config_json, {})
            if not isinstance(cfg, dict):
                continue
            if str(cfg.get("source") or "").strip() != src:
                continue
            if not match_event_config(cfg, body):
                continue
            run_id = await _start_automatic_run(
                wf,
                triggered_by=f"event:{src}",
                payload=body,
                trigger_depth=depth,
            )
            if run_id:
                started.append(run_id)
    except Exception as exc:
        logger.exception("fire_event failed source=%s tenant=%s: %s", source, tenant_id, exc)
    return started


def safe_fire_event(source: str, payload: dict, tenant_id: str, **kwargs: Any) -> None:
    """Fire-and-forget from sync/async request paths — never raises."""
    try:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(fire_event(source, payload or {}, tenant_id or "default", **kwargs))
        except RuntimeError:
            asyncio.run(fire_event(source, payload or {}, tenant_id or "default", **kwargs))
    except Exception as exc:
        logger.warning("safe_fire_event failed: %s", exc)


async def _schedule_job_callback(workflow_id: str, tenant_id: str) -> None:
    if not triggers_enabled():
        _audit_suppressed(
            workflow_id=workflow_id,
            tenant_id=tenant_id,
            reason="kill_switch on schedule tick",
            actor="schedule",
        )
        return
    with Session(engine) as session:
        wf = session.get(WorkflowDefinition, workflow_id)
        if not wf or not wf.enabled or wf.tenant_id != tenant_id:
            return
        if wf.trigger_type != "schedule":
            return
        session.expunge(wf)
    await _start_automatic_run(
        wf,
        triggered_by="schedule",
        payload={"source": "schedule", "workflow_id": workflow_id},
        trigger_depth=0,
    )


def _job_id(workflow_id: str) -> str:
    return f"{JOB_PREFIX}{workflow_id}"


def _apscheduler_cron_expr(cron: str) -> str:
    """Normalize standard crontab DOW (0=Sun) to APScheduler (0=Mon).

    APScheduler's CronTrigger.from_crontab passes day_of_week through unchanged
    but interprets numbers with Monday=0, so ``1-5`` becomes Tue–Sat unless
    we remap. Named ranges like ``mon-fri`` are left alone.
    """
    parts = (cron or "").strip().split()
    if len(parts) != 5:
        return (cron or "").strip()
    dow = parts[4]
    if any(ch.isalpha() for ch in dow):
        return " ".join(parts)

    def _map_token(tok: str) -> str:
        tok = tok.strip()
        if not tok:
            return tok
        if tok == "*":
            return tok
        if "/" in tok:
            base, step = tok.split("/", 1)
            return f"{_map_token(base)}/{step}"
        if "-" in tok:
            a, b = tok.split("-", 1)
            if a.isdigit() and b.isdigit():
                return f"{(int(a) - 1) % 7}-{(int(b) - 1) % 7}"
            return tok
        if tok.isdigit():
            return str((int(tok) - 1) % 7)
        return tok

    parts[4] = ",".join(_map_token(t) for t in dow.split(","))
    return " ".join(parts)


def _build_cron_trigger(cron: str, timezone_name: str = "UTC"):
    from apscheduler.triggers.cron import CronTrigger
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone_name or "UTC")
    except Exception:
        tz = timezone.utc
    expr = _apscheduler_cron_expr(cron)
    return CronTrigger.from_crontab(expr, timezone=tz)


def reload_schedule_jobs() -> int:
    """Rebuild all schedule trigger jobs on the shared APScheduler. Returns job count."""
    from ..cron_jobs import scheduler

    # Remove existing workflow schedule jobs
    try:
        for job in list(scheduler.get_jobs()):
            jid = str(getattr(job, "id", "") or "")
            if jid.startswith(JOB_PREFIX):
                try:
                    scheduler.remove_job(jid)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("reload_schedule_jobs remove failed: %s", exc)

    if not triggers_enabled():
        return 0

    count = 0
    with Session(engine) as session:
        rows = session.exec(
            select(WorkflowDefinition).where(
                WorkflowDefinition.enabled == True,  # noqa: E712
                WorkflowDefinition.trigger_type == "schedule",
            )
        ).all()
        for wf in rows:
            cfg = _parse_json(wf.trigger_config_json, {})
            cron = str((cfg or {}).get("cron") or "").strip()
            if not cron:
                continue
            tz_name = str((cfg or {}).get("timezone") or "UTC").strip() or "UTC"
            try:
                trigger = _build_cron_trigger(cron, tz_name)
                scheduler.add_job(
                    _schedule_job_callback,
                    trigger=trigger,
                    id=_job_id(wf.id),
                    replace_existing=True,
                    kwargs={"workflow_id": wf.id, "tenant_id": wf.tenant_id},
                    coalesce=True,
                    max_instances=1,
                )
                count += 1
            except Exception as exc:
                logger.warning(
                    "failed to register schedule job workflow_id=%s cron=%s: %s",
                    wf.id,
                    cron,
                    exc,
                )
    return count


def scheduled_job_count() -> int:
    from ..cron_jobs import scheduler

    try:
        return sum(
            1
            for job in scheduler.get_jobs()
            if str(getattr(job, "id", "") or "").startswith(JOB_PREFIX)
        )
    except Exception:
        return 0


def next_fire_times(cron: str, *, timezone_name: str = "UTC", count: int = 5) -> list[str]:
    """Return next N fire times as ISO strings (UTC)."""
    expr = (cron or "").strip()
    if not expr:
        return []
    try:
        trigger = _build_cron_trigger(expr, timezone_name)
        cursor = _now()
        out: list[str] = []
        for _ in range(max(1, min(count, 20))):
            nxt = trigger.get_next_fire_time(None, cursor)
            if nxt is None:
                break
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            out.append(nxt.astimezone(timezone.utc).isoformat())
            cursor = nxt + timedelta(seconds=1)
        return out
    except Exception:
        return []


def humanize_cron(cron: str) -> str:
    """Best-effort human readable cron summary."""
    parts = (cron or "").strip().split()
    if len(parts) != 5:
        return cron or ""
    minute, hour, dom, month, dow = parts
    if (
        minute.isdigit()
        and hour.isdigit()
        and dom == "*"
        and month == "*"
        and dow in {"1-5", "MON-FRI", "mon-fri"}
    ):
        return f"Every weekday at {int(hour):02d}:{int(minute):02d} UTC"
    if minute.isdigit() and hour.isdigit() and dom == "*" and month == "*" and dow == "*":
        return f"Every day at {int(hour):02d}:{int(minute):02d} UTC"
    if minute.startswith("*/") and hour == "*" and dom == "*" and month == "*" and dow == "*":
        return f"Every {minute[2:]} minutes"
    return f"Cron: {cron}"


async def drain_queued_for_workflow(workflow_id: str) -> None:
    """After a run finishes, start next queued automatic run if any."""
    with _queue_lock:
        q = _queued_runs.get(workflow_id)
        item = q.popleft() if q else None
    if not item:
        return
    with Session(engine) as session:
        wf = session.get(WorkflowDefinition, workflow_id)
        if not wf or not wf.enabled:
            return
        session.expunge(wf)
    await _start_automatic_run(
        wf,
        triggered_by=item.get("triggered_by") or "queue",
        payload=item.get("payload") or {},
        trigger_depth=int(item.get("trigger_depth") or 0),
    )


def triggers_status() -> dict[str, Any]:
    return {
        "triggers_enabled": triggers_enabled(),
        "scheduled_job_count": scheduled_job_count(),
        "event_sources": list(EVENT_SOURCES),
        "max_trigger_depth": MAX_TRIGGER_DEPTH,
        "env_default": (os.environ.get("WORKFLOWS_TRIGGERS_ENABLED") or "true"),
    }
