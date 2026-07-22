from prometheus_client import Counter, Histogram, Gauge, make_asgi_app

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


def record_connector_error(connector: str, error_type: str) -> None:
    try:
        CONNECTOR_ERRORS_TOTAL.labels(
            connector=connector or "unknown",
            error_type=error_type or "unknown",
        ).inc()
    except Exception:
        pass


def observe_health_probe(probe_name: str, duration_seconds: float) -> None:
    try:
        HEALTH_PROBE_DURATION_SECONDS.labels(
            probe_name=probe_name or "unknown",
        ).observe(max(0.0, float(duration_seconds)))
    except Exception:
        pass

