from __future__ import annotations

import os

from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from prometheus_client.core import REGISTRY, GaugeMetricFamily
from prometheus_client.registry import Collector


def _safe_label(value: str | None, *, max_len: int = 64, default: str = "unknown") -> str:
    """Sanitize prometheus label values so bad input never raises."""
    raw = (value or default).strip() or default
    # Prometheus label values shouldn't be huge; strip control chars.
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    return cleaned[:max_len] or default

INCIDENTS_TOTAL = Counter(
    "aiops_incidents_total",
    "Total incidents triaged",
    ["severity", "source", "outcome"],
)
AGENT_CONFIDENCE = Histogram(
    "aiops_agent_confidence_score",
    "Agent confidence score distribution",
    buckets=[0.1, 0.3, 0.5, 0.7, 0.85, 0.92, 1.0],
)
HITL_APPROVAL_SECONDS = Histogram(
    "aiops_hitl_approval_seconds",
    "Seconds from HITL trigger to human decision",
)
GUARDRAIL_BLOCKS_TOTAL = Counter(
    "aiops_guardrail_blocks_total",
    "Total commands blocked by safety guardrail",
    ["violation_type"],
)
LLM_LATENCY_SECONDS = Histogram(
    "aiops_llm_latency_seconds",
    "LLM inference latency per provider",
    ["provider"],
)
ACTIVE_APPROVALS = Gauge(
    "aiops_active_hitl_approvals",
    "Current incidents awaiting human approval",
)
# TODO: Add counters for AI actions:
# - ai_actions_blocked_total{violation_type}
# - ai_actions_approved_total
# - ai_actions_rejected_total
# - ai_actions_error_total
AI_ACTIONS_BLOCKED_TOTAL = Counter(
    "ai_actions_blocked_total",
    "AI-proposed actions blocked by guardrails",
    ["violation_type"],
)
AI_ACTIONS_APPROVED_TOTAL = Counter(
    "ai_actions_approved_total",
    "AI tool executions approved by a human",
)
AI_ACTIONS_REJECTED_TOTAL = Counter(
    "ai_actions_rejected_total",
    "AI tool executions rejected by a human",
)
AI_ACTIONS_ERROR_TOTAL = Counter(
    "ai_actions_error_total",
    "AI action parsing or execution failures",
)
HTTP_REQUESTS_TOTAL = Counter(
    "aiops_http_requests_total",
    "Total HTTP requests processed",
    ["method", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "aiops_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "status_code"],
)
# TODO(S3-P3.1): Add metrics for health probes and connector errors
CONNECTOR_ERRORS_TOTAL = Counter(
    "aiops_connector_errors_total",
    "Total connector errors by type",
    ["connector", "error_type"],
)
HEALTH_PROBE_DURATION_SECONDS = Histogram(
    "aiops_health_probe_duration_seconds",
    "Duration of health probes by name",
    ["probe_name"],
)
WEBHOOK_SIGNATURE_FAILURES_TOTAL = Counter(
    "webhook_signature_failures_total",
    "Webhook requests rejected due to invalid or missing HMAC signature",
)
WEBHOOK_DUPLICATES_TOTAL = Counter(
    "webhook_duplicates_total",
    "Webhook deliveries ignored as duplicates",
    ["source"],
)
ALERTS_SUPPRESSED_TOTAL = Counter(
    "alerts_suppressed_total",
    "Alerts suppressed by rules-based correlation",
    ["source", "rule_id"],
)
ALERTS_GROUPED_TOTAL = Counter(
    "alerts_grouped_total",
    "Alerts grouped into existing incidents by rules-based correlation",
    ["source", "rule_id"],
)
CELERY_TASK_RETRIES_TOTAL = Counter(
    "celery_task_retries_total",
    "Celery task retry attempts",
    ["task", "queue"],
)
CELERY_TASK_FAILURES_TOTAL = Counter(
    "celery_task_failures_total",
    "Celery tasks that exhausted retries (dead-lettered)",
    ["task", "queue"],
)
DEMO_DATA_SERVED_TOTAL = Counter(
    "demo_data_served_total",
    "Demo fixture responses served when ENABLE_DEMO_DATA/ENV allows",
    ["endpoint"],
)
GITHUB_API_REQUESTS_TOTAL = Counter(
    "github_api_requests_total",
    "GitHub API requests by operation and outcome status",
    ["operation", "status"],
)
LOGIN_FAILURES_TOTAL = Counter(
    "login_failures_total",
    "Failed login attempts (bad credentials, MFA, or lockout)",
    ["reason"],
)
# Alias-friendly name used in alert docs (signature rejects = webhook failures).
WEBHOOK_FAILURES_TOTAL = WEBHOOK_SIGNATURE_FAILURES_TOTAL


def record_connector_error(connector: str, error_type: str) -> None:
    try:
        CONNECTOR_ERRORS_TOTAL.labels(
            connector=_safe_label(connector),
            error_type=_safe_label(error_type),
        ).inc()
    except Exception:
        pass


def observe_health_probe(probe_name: str, duration_seconds: float) -> None:
    try:
        HEALTH_PROBE_DURATION_SECONDS.labels(
            probe_name=_safe_label(probe_name),
        ).observe(max(0.0, float(duration_seconds)))
    except Exception:
        pass


def record_webhook_signature_failure() -> None:
    try:
        WEBHOOK_SIGNATURE_FAILURES_TOTAL.inc()
    except Exception:
        pass


def record_webhook_duplicate(source: str) -> None:
    try:
        WEBHOOK_DUPLICATES_TOTAL.labels(source=_safe_label(source)).inc()
    except Exception:
        pass


def record_alert_suppressed(source: str, rule_id: str) -> None:
    try:
        ALERTS_SUPPRESSED_TOTAL.labels(
            source=_safe_label(source),
            rule_id=_safe_label(rule_id),
        ).inc()
    except Exception:
        pass


def record_alert_grouped(source: str, rule_id: str) -> None:
    try:
        ALERTS_GROUPED_TOTAL.labels(
            source=_safe_label(source),
            rule_id=_safe_label(rule_id),
        ).inc()
    except Exception:
        pass


def record_celery_task_retry(task: str, queue: str) -> None:
    try:
        CELERY_TASK_RETRIES_TOTAL.labels(
            task=_safe_label(task, max_len=128),
            queue=_safe_label(queue),
        ).inc()
    except Exception:
        pass


def record_celery_task_failure(task: str, queue: str) -> None:
    try:
        CELERY_TASK_FAILURES_TOTAL.labels(
            task=_safe_label(task, max_len=128),
            queue=_safe_label(queue),
        ).inc()
    except Exception:
        pass


def record_demo_data_served(endpoint: str) -> None:
    try:
        DEMO_DATA_SERVED_TOTAL.labels(endpoint=_safe_label(endpoint)).inc()
    except Exception:
        pass


def record_github_api_request(operation: str, status: str) -> None:
    try:
        GITHUB_API_REQUESTS_TOTAL.labels(
            operation=_safe_label(operation),
            status=_safe_label(status),
        ).inc()
    except Exception:
        pass


def record_login_failure(reason: str = "invalid_credentials") -> None:
    try:
        LOGIN_FAILURES_TOTAL.labels(reason=_safe_label(reason)).inc()
    except Exception:
        pass


def _redis_llen(queue: str) -> float:
    url = (
        (os.getenv("CELERY_BROKER_URL") or "").strip()
        or (os.getenv("REDIS_URL") or "").strip()
    )
    if not url:
        return 0.0
    try:
        import redis as redis_sync

        client = redis_sync.Redis.from_url(
            url, socket_connect_timeout=0.3, socket_timeout=0.3
        )
        return float(client.llen(queue) or 0)
    except Exception:
        return 0.0


class _CeleryQueueDepthCollector(Collector):
    """Scrape-time Redis LLEN for Celery queues (celery, triage, notify)."""

    def collect(self):
        metric = GaugeMetricFamily(
            "celery_queue_depth",
            "Approximate Celery broker queue depth (Redis LLEN)",
            labels=["queue"],
        )
        for queue in ("celery", "triage", "notify"):
            metric.add_metric([queue], _redis_llen(queue))
        yield metric


_CELERY_QUEUE_COLLECTOR_REGISTERED = False


def _ensure_celery_queue_collector() -> None:
    global _CELERY_QUEUE_COLLECTOR_REGISTERED
    if _CELERY_QUEUE_COLLECTOR_REGISTERED:
        return
    try:
        REGISTRY.register(_CeleryQueueDepthCollector())
        _CELERY_QUEUE_COLLECTOR_REGISTERED = True
    except ValueError:
        # Already registered (reload / multiple imports)
        _CELERY_QUEUE_COLLECTOR_REGISTERED = True


_ensure_celery_queue_collector()

