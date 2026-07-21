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

