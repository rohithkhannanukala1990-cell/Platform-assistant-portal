# ══════════════════════════════════════════════════════════
# Composition root — FastAPI app, middleware, router wiring.
# Business handlers live in backend/routers/* and services/*.
# ══════════════════════════════════════════════════════════

import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text as sa_text
from sqlmodel import Session
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount

from .auth import auth_router, seed_default_admin, seed_default_llm_config
from .database import create_db_and_tables, engine as db_engine
from .middleware.workspace_isolation import WorkspaceIsolationMiddleware
from .observability.logger import logger
from .observability.metrics import (
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    make_asgi_app,
)
from .rate_limit import limiter
from .routers import entity_actions as entity_actions_module
from .routers import golden_paths as golden_paths_module
from .routers import standards as standards_module
from .routers.ai_assistant import router as ai_router
from .routers.catalog import router as catalog_router
from .routers.catalog_copilot import router as catalog_copilot_router
from .routers.dashboard import router as dashboard_router
from .routers.github_ops import router as github_ops_router
from .routers.k8s_ops import router as k8s_ops_router
from .routers.pagerduty_ops import router as pagerduty_ops_router
from .routers.catalog_actions import router as catalog_actions_router
from .routers.slack_ops import router as slack_ops_router
from .routers.prometheus_ops import router as prometheus_ops_router
from .routers.outbound_webhook_ops import router as outbound_webhook_ops_router
from .routers.argocd_ops import router as argocd_ops_router
from .routers.servicenow_ops import router as servicenow_ops_router
from .routers.health_api import router as health_api_router
from .routers.imports_api import router as imports_api_router
from .routers.incidents import router as incidents_router
from .routers.infra_cicd import router as infra_cicd_router
from .routers.llm_config import router as llm_config_router
from .routers.mcp_api import router as mcp_api_router
from .routers.notifications import router as notifications_router
from .routers.oncall import router as oncall_router
from .routers.alert_rules import router as alert_rules_router
from .routers.platform_misc import router as platform_misc_router
from .routers.policies import router as policies_router
from .routers.rbac import router as rbac_router
from .routers.reports import router as reports_router
from .routers.scorecards import router as scorecards_router
from .routers.templates import router as templates_router
from .routers.tools import router as tools_router
from .routers.user_context import router as user_context_router
from .routers.webhooks_api import router as webhooks_api_router
from .routers.workspaces import router as workspaces_router

load_dotenv()

# Re-exports for Celery tasks (backend.tasks imports from main)
from .services.incidents_service import hitl_evaluate as _hitl_evaluate  # noqa: F401
from .services.incidents_service import run_triage as _run_triage  # noqa: F401
from .routers.webhooks_api import _map_to_cloud_event, _route_owner  # noqa: F401
from .services.demo_fixtures import CICD_MONITOR_SCENARIOS as _CICD_MONITOR_SCENARIOS  # noqa: F401


async def _wait_for_db(retries: int = 30, delay: float = 2.0):
    """
    Block startup until the database accepts connections.
    SQLite is always ready immediately; only PostgreSQL needs a retry loop.
    """
    from .database import _is_sqlite

    if _is_sqlite:
        logger.info("SQLite mode - skipping DB readiness wait")
        return
    for attempt in range(1, retries + 1):
        try:
            with Session(db_engine) as session:
                session.exec(sa_text("SELECT 1"))
            logger.info("PostgreSQL ready", extra={"attempt": attempt})
            return
        except Exception as exc:
            logger.warning("Waiting for database", extra={"attempt": attempt, "error": str(exc)})
            await asyncio.sleep(delay)
    raise RuntimeError("Database did not become ready in time. Aborting startup.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .cron_jobs import shutdown_scheduler, start_scheduler

    await _wait_for_db()
    create_db_and_tables()
    from sqlmodel import SQLModel

    from .database import engine as db_engine_ref
    from .routers.catalog import CatalogEntity, ServiceDependency  # noqa: F401
    from .routers.scorecards import ScorecardCheck  # noqa: F401
    from .routers.standards import (  # noqa: F401
        EntityStandardEvaluation,
        Standard,
        StandardCheck,
    )
    from .routers.entity_actions import (  # noqa: F401
        EntityAction,
        EntityActionRun,
    )
    from .routers.golden_paths import (  # noqa: F401
        GoldenPathRun,
        GoldenPathTemplate,
    )
    from .database import (  # noqa: F401
        Template,
        TemplateApplication,
        TemplateTool,
        UserAgentPermission,
        Workspace,
        WorkspaceMember,
        WorkspaceTool,
    )
    from .auth import AuditLog, User  # noqa: F401
    from .services.auth_sessions import AuthSession  # noqa: F401

    SQLModel.metadata.create_all(db_engine_ref)
    seed_default_admin()
    seed_default_llm_config()
    start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


app = FastAPI(title="AIOps Portal API", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
metrics_app = make_asgi_app()
app.router.routes.insert(0, Mount("/metrics", app=metrics_app, name="metrics"))

from .routers.agents import router as agents_router
from .routers.audit_log import router as audit_router
from .routers.users import router as users_router
from .routers.sso import router as sso_router
from .routers.auth_sessions import router as auth_sessions_router

app.include_router(auth_router)
app.include_router(auth_sessions_router)
app.include_router(workspaces_router)
app.include_router(templates_router)
app.include_router(rbac_router)
app.include_router(ai_router)
app.include_router(llm_config_router)
app.include_router(mcp_api_router)
app.include_router(agents_router)
app.include_router(audit_router, prefix="")
app.include_router(users_router, prefix="")
app.include_router(sso_router)
app.include_router(entity_actions_module.catalog_router)
app.include_router(entity_actions_module.runs_router)
app.include_router(entity_actions_module.router)
app.include_router(golden_paths_module.runs_router)
app.include_router(golden_paths_module.router)
app.include_router(reports_router)
app.include_router(catalog_copilot_router)
app.include_router(standards_module.catalog_router)
app.include_router(standards_module.router)
app.include_router(catalog_router)
app.include_router(catalog_actions_router)
app.include_router(scorecards_router)
app.include_router(dashboard_router)
app.include_router(incidents_router)
app.include_router(webhooks_api_router)
app.include_router(notifications_router)
app.include_router(tools_router)
app.include_router(imports_api_router)
app.include_router(user_context_router)
app.include_router(infra_cicd_router)
app.include_router(health_api_router)
app.include_router(platform_misc_router)
app.include_router(github_ops_router)
app.include_router(k8s_ops_router)
app.include_router(pagerduty_ops_router)
app.include_router(slack_ops_router)
app.include_router(prometheus_ops_router)
app.include_router(outbound_webhook_ops_router)
app.include_router(argocd_ops_router)
app.include_router(servicenow_ops_router)
app.include_router(oncall_router)
app.include_router(alert_rules_router)
app.include_router(policies_router)

from .ws_portal import router as ws_portal_router

app.include_router(ws_portal_router)

app.add_middleware(WorkspaceIsolationMiddleware)


def _cors_allow_origins() -> list[str]:
    raw = (os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL") or "").strip()
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # Never allow wildcard with credentials
    origins = [o for o in origins if o != "*"]
    env = (os.getenv("ENV") or "dev").strip().lower()
    if env in {"production", "prod", "dr"}:
        if not origins:
            logger.error(
                "ALLOWED_ORIGINS/FRONTEND_URL unset in production — CORS deny-all (no * fallback)"
            )
            return []
        return origins
    if origins:
        return origins
    return [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://frontend:5173",
    ]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled error",
        extra={
            "path": request.url.path,
            "method": request.method,
            "request_id": getattr(request.state, "request_id", None),
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_seconds = time.perf_counter() - start
    duration_ms = round(duration_seconds * 1000, 3)
    status_code = str(response.status_code)
    try:
        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            status_code=status_code,
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            status_code=status_code,
        ).observe(duration_seconds)
    except Exception:
        pass  # never let bad prometheus labels break the request
    logger.info(
        "HTTP request",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": getattr(getattr(request.state, "user", None), "username", None),
            "workspace_id": getattr(request.state, "workspace_id", None),
        },
    )
    return response


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    from .observability.logger import clear_request_context, set_request_context

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    set_request_context(request_id=request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_request_context()


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "img-src 'self' data:; "
        "font-src 'self' data:"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.websocket("/ws/portal")
async def portal_ws(
    websocket: WebSocket,
    user_id: str = Query(default="anonymous"),
):
    from .ws_portal import accept_portal_connection

    await accept_portal_connection(websocket, user_id=user_id)
