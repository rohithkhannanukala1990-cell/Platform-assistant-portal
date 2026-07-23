"""Webhook log ingestion and inbound gateway."""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import User, get_current_user
from ..database import get_recent_webhook_events, save_webhook_event, update_webhook_event
from ..observability.logger import logger
from ..rate_limit import limiter
from ..services import incidents_service
from ..tasks import process_inbound_webhook, process_webhook_log
from ..webhooks.security import require_valid_signature

router = APIRouter(tags=["webhooks"])

async def _webhook_background_fallback(log_text: str, source: str):
    """In-process fallback used when Redis/Celery is unavailable (local dev)."""
    try:
        await incidents_service.run_triage(log_text, source=f"webhook:{source}")
    except Exception as exc:
        logger.error("Webhook fallback triage failed", extra={"source": source, "error": str(exc)})


async def _inbound_webhook_background_fallback(payload: dict, source: str, event_id: int):
    """In-process fallback for the inbound gateway when Redis/Celery is unavailable."""
    try:
        _event_type, log_text, _ = _map_to_cloud_event(payload, source)
        owner_role = _route_owner(source)
        result = await incidents_service.run_triage(log_text, source=f"webhook:{source}", owner_role=owner_role)
        update_webhook_event(event_id, status="processed", incident_id=result.get("id"))
    except Exception as exc:
        update_webhook_event(event_id, status="error")
        logger.error("Webhook fallback triage failed", extra={"source": source, "error": str(exc)})

class WebhookLogRequest(BaseModel):
    source:    str
    log_text:  str
    timestamp: str | None = None


@router.post("/api/webhooks/logs", status_code=202)
@limiter.limit("5/minute")
async def ingest_webhook_log(request: Request, body: WebhookLogRequest, current_user: User = Depends(get_current_user)):
    """Accept a log payload, return 202 immediately, dispatch Celery task for triage."""
    if not body.log_text.strip():
        raise HTTPException(status_code=400, detail="log_text cannot be empty.")
    if not body.source.strip():
        raise HTTPException(status_code=400, detail="source cannot be empty.")

    raw_body = await request.body()
    require_valid_signature(body.source.strip().lower(), raw_body, dict(request.headers))

    try:
        task = process_webhook_log.delay(body.log_text, body.source.strip())
        task_id = task.id
    except Exception:
        # Redis not available in local dev — fall back to in-process background task
        asyncio.create_task(_webhook_background_fallback(body.log_text, body.source.strip()))
        task_id = "local-fallback"

    return {
        "status":  "accepted",
        "task_id": task_id,
        "message": f"Log from '{body.source}' queued for triage.",
    }

_ROLE_ROUTES: dict[str, str] = {
    # Developer
    "github":       "Developer",
    "gitlab":       "Developer",
    "jira":         "Developer",
    "cypress":     "Developer",
    "playwright":  "Developer",
    "sonarqube":   "Developer",
    "codecov":     "Developer",
    "testrail":    "Developer",
    "jest":        "Developer",
    # Data Engineer
    "airflow":      "DataEngineer",
    "snowflake":    "DataEngineer",
    "dbt":          "DataEngineer",
    "kafka":        "DataEngineer",
    # Network Engineer
    "aws":          "NetworkEngineer",
    "datadog":      "NetworkEngineer",
    "pagerduty":    "NetworkEngineer",
    "cloudwatch":   "NetworkEngineer",
    # SRE/Platform
    "prometheus":    "NetworkEngineer",
    "alertmanager":  "NetworkEngineer",
    "grafana":       "NetworkEngineer",
    "argocd":        "NetworkEngineer",
    "flux":          "NetworkEngineer",
    "kubernetes":    "NetworkEngineer",
    "newrelic":      "NetworkEngineer",
    "splunk":        "NetworkEngineer",
    "opsgenie":      "NetworkEngineer",
    # Security
    "falco":         "NetworkEngineer",
    "snyk":          "Developer",
    "sentry":        "Developer",
    "dependabot":    "Developer",
    "trivy":       "Developer",
    "semgrep":     "Developer",
    "checkov":     "NetworkEngineer",
    # CI/CD
    "circleci":      "Developer",
    "jenkins":       "Developer",
    "harness":       "Developer",
    "bitbucket":     "Developer",
    "travis":        "Developer",
    # Database Developer
    "aws rds":      "DatabaseDeveloper",
    "rds":          "DatabaseDeveloper",
    "mongodb":      "DatabaseDeveloper",
    "postgresql":   "DatabaseDeveloper",
    "postgres":     "DatabaseDeveloper",
    "mysql":        "DatabaseDeveloper",
    "redis":        "DatabaseDeveloper",
    "clickhouse":   "DatabaseDeveloper",
    "elasticsearch":"DatabaseDeveloper",
    # Database
    "cassandra":     "DatabaseDeveloper",
    "dynamodb":      "DatabaseDeveloper",
}

def _route_owner(source: str) -> str:
    return _ROLE_ROUTES.get(source.lower(), "Admin")


def _map_to_cloud_event(payload: dict, source: str) -> tuple[str, str, str]:
    """
    Extract (event_type, log_text, cloud_event_id) from an arbitrary inbound payload.
    Tries common keys from GitHub, Datadog, Airflow, Snowflake, AWS SNS, etc.
    Falls back to JSON-dumping the entire payload as the log text.
    """
    import uuid, json as _json

    # --- event type inference ---
    event_type = (
        payload.get("action")                        # GitHub
        or payload.get("alert_type")                 # Datadog
        or payload.get("event")                      # generic
        or payload.get("dag_id")                     # Airflow
        or payload.get("Type")                       # AWS SNS
        or "inbound_event"
    )

    # --- log text extraction ---
    candidates = [
        payload.get("message"),                      # generic
        payload.get("body"),                         # Datadog / PagerDuty
        payload.get("detail"),                       # AWS EventBridge
        payload.get("Message"),                      # AWS SNS JSON inside message
        payload.get("head_commit", {}).get("message") if isinstance(payload.get("head_commit"), dict) else None,  # GitHub push
        payload.get("description"),
        payload.get("alerts", [{}])[0].get("annotations", {}).get("summary") if isinstance(payload.get("alerts"), list) else None,  # Prometheus AlertManager
        payload.get("evalMatches", [{}])[0].get("title") if isinstance(payload.get("evalMatches"), list) else None,  # Grafana
        payload.get("output"),   # Falco
        payload.get("issue", {}).get("title") if isinstance(payload.get("issue"), dict) else None,  # Snyk
        payload.get("app", {}).get("name") if isinstance(payload.get("app"), dict) else None,  # ArgoCD
    ]
    log_text = next((c for c in candidates if c), None)
    if not log_text:
        log_text = f"Inbound webhook event from {source}:\n{_json.dumps(payload, indent=2)}"

    cloud_event_id = str(uuid.uuid4())
    return str(event_type), log_text, cloud_event_id

class InboundWebhookRequest(BaseModel):
    """Docs / OpenAPI shape only — inbound gateway verifies HMAC over raw request bytes."""

    source: str
    payload: dict = {}
    event_type: str | None = None


@router.post("/api/webhooks/inbound", status_code=202)
@limiter.limit("5/minute")
async def inbound_webhook_gateway(request: Request):
    """
    Queue-first webhook gateway.
    Accepts any source+payload, returns 202 immediately,
    dispatches a Celery task for normalization + AI triage.
    HMAC is verified against the raw request body (not str(payload)).
    """
    import json as _json
    import uuid

    raw_body = await request.body()
    try:
        data = _json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    source = str(data.get("source") or "").strip().lower()
    if not source:
        raise HTTPException(status_code=400, detail="source cannot be empty.")

    require_valid_signature(source, raw_body, dict(request.headers))

    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    event_type = data.get("event_type") or _map_to_cloud_event(payload, source)[0]
    owner_role = _route_owner(source)
    ce_id = str(uuid.uuid4())

    ev = save_webhook_event({
        "source":         source,
        "event_type":     event_type,
        "owner_role":     owner_role,
        "status":         "accepted",
        "raw_payload":    _json.dumps(payload),
        "cloud_event_id": ce_id,
    })

    try:
        task = process_inbound_webhook.delay(payload, source, ev.id)
        task_id = task.id
    except Exception:
        # Redis not available in local dev — fall back to in-process coroutine
        asyncio.create_task(_inbound_webhook_background_fallback(payload, source, ev.id))
        task_id = "local-fallback"

    return {
        "status":         "accepted",
        "task_id":        task_id,
        "cloud_event_id": ce_id,
        "routed_to":      owner_role,
        "message":        f"Event from '{source}' accepted and queued for processing.",
    }


@router.get("/api/webhooks/activity")
def webhook_activity(limit: int = 40, current_user: User = Depends(get_current_user)):
    return get_recent_webhook_events(limit=limit)