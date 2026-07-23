# ══════════════════════════════════════════════════════════
# SPRINT 10 AUDIT NOTE (May 2026)
# All routers verified and registered.
# Sprint 11 refactor candidates (extract from main.py):
#   - Incident management section
#   - Agent/HITL approval section
#   - Health check aggregation section
#   - DORA metrics section
# ══════════════════════════════════════════════════════════

import os
import re
import json
import asyncio
import time
import uuid
import httpx
import ollama
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, WebSocket, Query
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .middleware.workspace_isolation import WorkspaceIsolationMiddleware
from pydantic import BaseModel
from google import genai
from sqlmodel import Session, select
from sqlalchemy import text as sa_text
from .database import engine as db_engine
from .auth import auth_router, get_current_user, write_audit, User, require_admin, require_role
from .auth import seed_default_admin, seed_default_llm_config
from .command_validator import CommandValidator
from .executor.safe_executor import safe_executor
from .tasks import process_inbound_webhook, process_webhook_log
from .webhooks.security import require_valid_signature
from .observability.metrics import (
    INCIDENTS_TOTAL, LLM_LATENCY_SECONDS, AGENT_CONFIDENCE,
    GUARDRAIL_BLOCKS_TOTAL, ACTIVE_APPROVALS, HITL_APPROVAL_SECONDS,
    HTTP_REQUESTS_TOTAL, HTTP_REQUEST_DURATION_SECONDS, make_asgi_app
)
from .observability.logger import logger
from .database import (
    create_db_and_tables,
    save_incident, get_all_incidents, update_incident_status, serialize_incident,
    save_infra,    get_all_infra,
    save_cicd,     get_all_cicd,
    get_settings,  update_settings,
    create_notification, get_all_notifications, mark_notification_read,
    save_webhook_event, update_webhook_event, get_recent_webhook_events,
    get_pending_approvals,
    HealthAlert,
    Tool,
)
from .routers.workspaces import router as workspaces_router
from .routers.templates import router as templates_router
from .routers.rbac import router as rbac_router
from .routers.ai_assistant import router as ai_router
from .routers.catalog import router as catalog_router
from .routers.scorecards import router as scorecards_router
from .routers import standards as standards_module
from .routers import entity_actions as entity_actions_module
from .routers import golden_paths as golden_paths_module
from .routers.reports import router as reports_router
from .routers.catalog_copilot import router as catalog_copilot_router
from .routers.dashboard import router as dashboard_router
from .rate_limit import limiter
from .routers.incidents import router as incidents_router
from .routers.webhooks_api import router as webhooks_api_router
from .routers.notifications import router as notifications_router
from .routers.tools import router as tools_router
from .routers.imports_api import router as imports_api_router
from .routers.user_context import router as user_context_router

load_dotenv()

from .services.incidents_service import hitl_evaluate as _hitl_evaluate, to_list as _to_list
from .services.incidents_service import run_triage as _run_triage  # noqa: F401 — Celery tasks
from .routers.webhooks_api import _map_to_cloud_event, _route_owner  # noqa: F401 — Celery tasks

# ── Provider config ──────────────────────────────────────────────────────────
# Default to Ollama so the backend can boot without cloud credentials.
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

gemini_client = None
if AI_PROVIDER == "gemini":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        # Don't crash the whole API for local/dev usage; fall back to Ollama.
        logger.warning("GEMINI_API_KEY not set - falling back to ollama")
        AI_PROVIDER = "ollama"
    else:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

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
    from .routers.catalog import CatalogEntity, ServiceDependency  # noqa: F401 — register table metadata
    from .routers.scorecards import ScorecardCheck  # noqa: F401 — register table metadata
    from .routers.standards import (  # noqa: F401 — register table metadata
        EntityStandardEvaluation,
        Standard,
        StandardCheck,
    )
    from .routers.entity_actions import (  # noqa: F401 — register table metadata
        EntityAction,
        EntityActionRun,
    )
    from .routers.golden_paths import (  # noqa: F401 — register table metadata
        GoldenPathRun,
        GoldenPathTemplate,
    )
    from .database import (  # noqa: F401 — workspace/template tables (database.py)
        Template,
        TemplateApplication,
        TemplateTool,
        UserAgentPermission,
        Workspace,
        WorkspaceMember,
        WorkspaceTool,
    )
    from .auth import AuditLog, User  # noqa: F401

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
from starlette.routing import Mount
app.router.routes.insert(0, Mount("/metrics", app=metrics_app, name="metrics"))
# Sprint 10: router registration audit — all backend/routers/*.py modules included
app.include_router(auth_router)
app.include_router(workspaces_router)
app.include_router(templates_router)
app.include_router(rbac_router)
app.include_router(ai_router)
from .routers.agents import router as agents_router
from .routers.audit_log import router as audit_router
from .routers.users import router as users_router
from .routers.sso import router as sso_router
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
app.include_router(scorecards_router)
app.include_router(dashboard_router)
app.include_router(incidents_router)
app.include_router(webhooks_api_router)
app.include_router(notifications_router)
app.include_router(tools_router)
app.include_router(imports_api_router)
app.include_router(user_context_router)
# Sprint 6: enforce RBAC on selected routes via Depends(require_permission("resource", "action"))
# from .middleware.rbac_middleware import require_permission

app.add_middleware(WorkspaceIsolationMiddleware)


def _cors_allow_origins() -> list[str]:
    raw = (os.getenv("ALLOWED_ORIGINS") or os.getenv("FRONTEND_URL") or "").strip()
    origins = [o.strip() for o in raw.split(",") if o.strip()]
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


# TODO: Harden global exception handling:
# - Log full exception details via observability.logger.logger.exception(...)
# - Return a generic error message to clients without exposing str(exc)
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


# TODO: Replace print-based request logging with structured logging:
# - Use observability.logger.logger.info(...)
# - Include method, path, status_code, duration_ms, user_id, workspace_id
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_seconds = time.perf_counter() - start
    duration_ms = round(duration_seconds * 1000, 3)
    status_code = str(response.status_code)
    HTTP_REQUESTS_TOTAL.labels(
        method=request.method,
        status_code=status_code,
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=request.method,
        status_code=status_code,
    ).observe(duration_seconds)
    logger.info(
        "HTTP request",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "user_id": getattr(
                getattr(request.state, "user", None), "username", None
            ),
            "workspace_id": getattr(request.state, "workspace_id", None),
        },
    )
    return response


# TODO: Add request_id to each request for correlation across logs
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


# ── System prompt ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior DevOps and SRE engineer embedded inside Cursor IDE.
Analyze the provided server logs and return ONLY a valid JSON object — no markdown, no explanation, no code fences.

The JSON must have exactly these keys:

{
  "severity": "<Critical | High | Medium | Low>",
  "summary": "<One sentence describing what is broken and the immediate impact.>",
  "root_cause": "<2-4 sentences. State the failing component, the technical reason it failed, and blast radius. Reference specific error codes or service names from the logs. Do not restate the logs — explain WHY.>",
  "evidence": [
    "<Specific log line or pattern that proves the root cause>",
    "<Another supporting log entry>"
  ],
  "action_plan": [
    "Immediate: <One action to stop active damage right now with the exact command or config change.>",
    "Fix: <The permanent code, config, or infra change — specify the file and what to change.>",
    "Harden: <One monitoring or alerting improvement to prevent recurrence.>"
  ],
  "commands": [
    "<exact shell command 1>",
    "<exact shell command 2>"
  ],
  "files_to_check": [
    "<file path or k8s resource> (<reason>)",
    "<file path or k8s resource> (<reason>)"
  ],
  "validation_steps": [
    "<Exact command or log pattern to confirm the fix worked>",
    "<Metric or threshold to verify system health>"
  ]
}

Rules:
- Use real inferred values from the logs. Do not use placeholder strings like <namespace> or <your-service>.
- The commands array must contain runnable shell/kubectl/psql/docker commands only — no prose.
- Return ONLY the JSON object. Nothing before or after it."""


# ── Pydantic models ──────────────────────────────────────────────────────────


# ── AI provider calls ────────────────────────────────────────────────────────
async def call_ollama(logs: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": logs},
        ],
    )
    return response.message.content


async def call_gemini(logs: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    prompt = f"{system_prompt}\n\nLogs to analyze:\n{logs}"
    result = gemini_client.models.generate_content(
        model="gemma-3-27b-it",
        contents=prompt,
    )
    return result.text







# ── Infra Builder ─────────────────────────────────────────────────────────────

PROVIDER_CONTEXT = {
    "AWS": {
        "full_name": "Amazon Web Services",
        "tf_provider": 'terraform {\n  required_providers {\n    aws = {\n      source  = "hashicorp/aws"\n      version = "~> 5.0"\n    }\n  }\n}\nprovider "aws" {\n  region = "us-east-1"\n}',
        "tf_resources": "aws_instance, aws_s3_bucket, aws_db_instance, aws_vpc, aws_subnet, aws_security_group, aws_iam_role",
        "cli_tool": "AWS CLI (aws)",
        "cli_examples": "aws ec2 run-instances, aws s3 mb, aws rds create-db-instance",
        "free_tier": "t2.micro/t3.micro EC2 (750 hrs/month), 5GB S3, 750hrs RDS db.t2.micro",
        "default_region": "us-east-1",
    },
    "GCP": {
        "full_name": "Google Cloud Platform",
        "tf_provider": 'terraform {\n  required_providers {\n    google = {\n      source  = "hashicorp/google"\n      version = "~> 5.0"\n    }\n  }\n}\nprovider "google" {\n  project = "my-project-id"\n  region  = "us-central1"\n}',
        "tf_resources": "google_compute_instance, google_storage_bucket, google_sql_database_instance, google_container_cluster, google_cloud_run_service",
        "cli_tool": "gcloud CLI",
        "cli_examples": "gcloud compute instances create, gcloud storage buckets create, gcloud sql instances create",
        "free_tier": "e2-micro in us-central1 (1 per month free), 5GB Cloud Storage, f1-micro Cloud SQL",
        "default_region": "us-central1",
    },
    "Azure": {
        "full_name": "Microsoft Azure",
        "tf_provider": 'terraform {\n  required_providers {\n    azurerm = {\n      source  = "hashicorp/azurerm"\n      version = "~> 3.0"\n    }\n  }\n}\nprovider "azurerm" {\n  features {}\n}',
        "tf_resources": "azurerm_virtual_machine, azurerm_storage_account, azurerm_sql_server, azurerm_resource_group, azurerm_virtual_network, azurerm_app_service",
        "cli_tool": "Azure CLI (az)",
        "cli_examples": "az vm create, az storage account create, az sql server create",
        "free_tier": "B1s VM (750 hrs/month free for 12 months), 5GB Blob Storage, Azure SQL 250GB",
        "default_region": "eastus",
    },
    "DigitalOcean": {
        "full_name": "DigitalOcean",
        "tf_provider": 'terraform {\n  required_providers {\n    digitalocean = {\n      source  = "digitalocean/digitalocean"\n      version = "~> 2.0"\n    }\n  }\n}\nprovider "digitalocean" {\n  token = var.do_token\n}',
        "tf_resources": "digitalocean_droplet, digitalocean_spaces_bucket, digitalocean_database_cluster, digitalocean_vpc, digitalocean_firewall, digitalocean_app",
        "cli_tool": "doctl CLI",
        "cli_examples": "doctl compute droplet create, doctl spaces create, doctl databases create",
        "free_tier": "No permanent free tier — cheapest Droplet is $4/month (512MB RAM). $200 credit for new accounts.",
        "default_region": "nyc3",
    },
}

INFRA_SYSTEM_PROMPT_TEMPLATE = """You are a Senior Multi-Cloud Architect with deep expertise in {full_name} infrastructure.
The user will describe the infrastructure they need. Generate production-ready Terraform and CLI commands SPECIFICALLY for {full_name}.
Return ONLY a valid JSON object — no markdown, no explanation, no code fences.

The JSON must have exactly these keys:

{{
  "resource_name": "<short descriptive name, e.g. '{provider} Free-Tier Web Server'>",
  "provider_used": "{provider}",
  "terraform_code": "<complete runnable HCL. Start with the provider block then resource blocks. Use these resource types: {tf_resources}. Use free-tier eligible sizes wherever possible. Escape all quotes inside the string.>",
  "cli_commands": [
    "<exact {cli_tool} command 1>",
    "<exact {cli_tool} command 2>",
    "<exact {cli_tool} command 3>"
  ],
  "cost_estimate": "<Free tier: {free_tier}. State the exact monthly cost for anything outside free tier. Be concise and practical.>"
}}

Rules:
- terraform_code must start with the provider block: {tf_provider_hint}
- Use the default region {default_region} unless the user specifies otherwise.
- cli_commands must use the {cli_tool} — example patterns: {cli_examples}
- All commands must be exact and copy-pasteable with no placeholder syntax like <your-value>.
- Return ONLY the JSON object. Nothing before or after it."""


class InfraRequest(BaseModel):
    prompt: str
    provider: str = "GCP"


class InfraResponse(BaseModel):
    resource_name: str
    provider_used: str
    terraform_code: str
    cli_commands: list[str]
    cost_estimate: str
    model_used: str


def build_infra_prompt(provider: str) -> str:
    ctx = PROVIDER_CONTEXT.get(provider.strip(), PROVIDER_CONTEXT["GCP"])
    return INFRA_SYSTEM_PROMPT_TEMPLATE.format(
        full_name=ctx["full_name"],
        provider=provider,
        tf_resources=ctx["tf_resources"],
        cli_tool=ctx["cli_tool"],
        cli_examples=ctx["cli_examples"],
        free_tier=ctx["free_tier"],
        default_region=ctx["default_region"],
        tf_provider_hint=ctx["tf_provider"].split("\n")[0],
    )


def parse_infra_response(text: str, provider: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "resource_name": str(data.get("resource_name", "Unnamed Resource")),
            "provider_used": str(data.get("provider_used", provider)),
            "terraform_code": str(data.get("terraform_code", "")),
            "cli_commands":  _to_list(data.get("cli_commands", [])),
            "cost_estimate": str(data.get("cost_estimate", "")),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "resource_name": "Parse Error — Raw Output",
            "provider_used": provider,
            "terraform_code": text,
            "cli_commands":  [],
            "cost_estimate": "Could not parse cost estimate.",
        }


@app.post("/api/infra/generate", response_model=InfraResponse)
@limiter.limit("5/minute")
async def generate_infra(request: Request, infra_in: InfraRequest, current_user: User = Depends(get_current_user)):
    if not infra_in.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    provider      = infra_in.provider.strip() or "GCP"
    system_prompt = build_infra_prompt(provider)
    user_msg      = f"Infrastructure request: {infra_in.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
            )
            raw_text   = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            full_prompt = f"{system_prompt}\n\n{user_msg}"
            result      = gemini_client.models.generate_content(model="gemma-3-27b-it", contents=full_prompt)
            raw_text    = result.text
            model_used  = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_infra_response(raw_text, provider)

    save_infra({
        **parsed,
        "prompt":     infra_in.prompt,
        "model_used": model_used,
    })

    return InfraResponse(
        resource_name=parsed["resource_name"],
        provider_used=parsed["provider_used"],
        terraform_code=parsed["terraform_code"],
        cli_commands=parsed["cli_commands"],
        cost_estimate=parsed["cost_estimate"],
        model_used=model_used,
    )


@app.get("/api/infra/history")
def list_infra(current_user: User = Depends(get_current_user)):
    return get_all_infra()


# ── CI/CD Pipeline Generator ─────────────────────────────────────────────────

CICD_TOOL_CONTEXT = {
    "GitHub Actions": {
        "file": ".github/workflows/main.yml",
        "format": "YAML",
        "syntax_hints": "Uses 'on', 'jobs', 'steps', 'uses', 'run' keywords. Jobs run on 'ubuntu-latest' by default. Secrets via ${{ secrets.NAME }}.",
        "stage_pattern": "jobs > build/test/deploy each with 'steps'",
        "example_stages": "checkout, setup language, install deps, run tests, build artifact, deploy",
    },
    "GitLab CI": {
        "file": ".gitlab-ci.yml",
        "format": "YAML",
        "syntax_hints": "Uses 'stages', 'image', 'script', 'only', 'artifacts', 'cache' keywords. Variables via $VARIABLE_NAME.",
        "stage_pattern": "stages list at top, then job blocks referencing each stage",
        "example_stages": "build, test, lint, security-scan, deploy",
    },
    "Jenkins": {
        "file": "Jenkinsfile",
        "format": "Groovy (Declarative Pipeline)",
        "syntax_hints": "Uses 'pipeline', 'agent', 'stages', 'stage', 'steps', 'sh', 'environment', 'post' blocks. Secrets via credentials().",
        "stage_pattern": "pipeline > stages > stage('Name') { steps { sh '...' } }",
        "example_stages": "Checkout, Build, Test, Code Analysis, Docker Build, Deploy",
    },
}

CICD_SYSTEM_PROMPT_TEMPLATE = """You are a Senior Release Engineer and DevOps expert specializing in CI/CD pipelines.
The user will describe their application and deployment target. Generate a production-ready {tool} pipeline.
Return ONLY a valid JSON object — no markdown, no explanation, no code fences.

Pipeline file: {file}
Format: {format}
Syntax guide: {syntax_hints}
Stage pattern: {stage_pattern}
Recommended stages: {example_stages}

The JSON must have exactly these keys:

{{
  "tool_name": "{tool}",
  "yaml_code": "<The complete {format} pipeline as a single string. Use \\n for newlines. Include all stages: install, lint, test, build, and deploy. Add comments explaining non-obvious steps. Make it production-ready, not a skeleton.>",
  "explanation": "<3-5 sentences explaining what each stage does, why the order matters, and any environment variables or secrets the user needs to configure.>",
  "security_checks": [
    "<Security or quality step 1 — e.g. dependency vulnerability scan>",
    "<Security or quality step 2 — e.g. SAST/static analysis>",
    "<Security or quality step 3 — e.g. Docker image scanning or secret detection>"
  ]
}}

Rules:
- yaml_code must be the FULL pipeline — never truncate or use placeholder comments like '# add more steps here'.
- Include at minimum: dependency install, unit tests, lint, build/package, deploy stages.
- Use environment variables and secrets correctly for {tool}.
- security_checks must be 3 specific items referencing tools or commands in the pipeline.
- Return ONLY the JSON object. Nothing before or after it."""


class CICDRequest(BaseModel):
    prompt: str
    cicd_tool: str = "GitHub Actions"


class CICDResponse(BaseModel):
    tool_name: str
    yaml_code: str
    explanation: str
    security_checks: list[str]
    model_used: str


def parse_cicd_response(text: str, tool: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "tool_name":       str(data.get("tool_name", tool)),
            "yaml_code":       str(data.get("yaml_code", text)),
            "explanation":     str(data.get("explanation", "")),
            "security_checks": _to_list(data.get("security_checks", [])),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "tool_name":       tool,
            "yaml_code":       text,
            "explanation":     "Could not parse structured explanation.",
            "security_checks": [],
        }


@app.post("/api/cicd/generate", response_model=CICDResponse)
@limiter.limit("5/minute")
async def generate_cicd(request: Request, cicd_in: CICDRequest, current_user: User = Depends(get_current_user)):
    if not cicd_in.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    tool = cicd_in.cicd_tool.strip() or "GitHub Actions"
    ctx  = CICD_TOOL_CONTEXT.get(tool, CICD_TOOL_CONTEXT["GitHub Actions"])

    system_prompt = CICD_SYSTEM_PROMPT_TEMPLATE.format(
        tool=tool,
        file=ctx["file"],
        format=ctx["format"],
        syntax_hints=ctx["syntax_hints"],
        stage_pattern=ctx["stage_pattern"],
        example_stages=ctx["example_stages"],
    )
    user_msg = f"Application description: {cicd_in.prompt}"

    try:
        if AI_PROVIDER == "ollama":
            response   = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
            )
            raw_text   = response.message.content
            model_used = "Ollama / Gemma 3 4B (Local)"
        else:
            result     = gemini_client.models.generate_content(
                model="gemma-3-27b-it",
                contents=f"{system_prompt}\n\n{user_msg}",
            )
            raw_text   = result.text
            model_used = "Gemma 3 27B (Cloud)"
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    parsed = parse_cicd_response(raw_text, tool)

    save_cicd({
        **parsed,
        "prompt":     cicd_in.prompt,
        "model_used": model_used,
    })

    return CICDResponse(
        tool_name=parsed["tool_name"],
        yaml_code=parsed["yaml_code"],
        explanation=parsed["explanation"],
        security_checks=parsed["security_checks"],
        model_used=model_used,
    )


@app.get("/api/cicd/history")
def list_cicd(current_user: User = Depends(get_current_user)):
    return get_all_cicd()


@app.get("/api/settings")
def fetch_settings(current_user: User = Depends(get_current_user)):
    return get_settings()


@app.post("/api/settings")
@limiter.limit("5/minute")
def save_settings(request: Request, body: dict, current_user: User = Depends(get_current_user)):
    return update_settings(body)


@app.get("/api/analytics")
def get_analytics(current_user: User = Depends(get_current_user)):
    from collections import Counter
    from datetime import datetime, timezone, timedelta

    incidents  = get_all_incidents()
    infra_list = get_all_infra()
    cicd_list  = get_all_cicd()
    notifs     = get_all_notifications()

    # ── Basic counts ──────────────────────────────────────────────────────────
    total_incidents   = len(incidents)
    critical_alerts   = sum(1 for i in incidents if i["severity"] == "Critical")
    unread_notifs     = sum(1 for n in notifs if not n["is_read"])

    # ── Incidents by severity ─────────────────────────────────────────────────
    severity_order = ["Critical", "High", "Medium", "Warning", "Low", "Unknown"]
    sev_counter    = Counter(i["severity"] for i in incidents)
    incidents_by_severity = [
        {"name": s, "value": sev_counter.get(s, 0)}
        for s in severity_order if sev_counter.get(s, 0) > 0
    ]

    # ── Top sources ───────────────────────────────────────────────────────────
    src_counter = Counter(
        (i.get("source") or "manual").replace("webhook:", "") for i in incidents
    )
    top_sources = [
        {"name": src, "value": cnt}
        for src, cnt in src_counter.most_common(8)
    ]

    # ── Incidents over last 7 days ────────────────────────────────────────────
    now  = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%b %d") for i in range(6, -1, -1)]
    day_counter: dict[str, int] = {d: 0 for d in days}
    for inc in incidents:
        try:
            ts  = datetime.fromisoformat(inc["timestamp"])
            key = ts.strftime("%b %d")
            if key in day_counter:
                day_counter[key] += 1
        except Exception:
            pass
    incidents_over_time = [{"date": d, "count": day_counter[d]} for d in days]

    # ── Module activity ───────────────────────────────────────────────────────
    module_activity = [
        {"name": "Alerts",    "value": total_incidents},
        {"name": "Infra",     "value": len(infra_list)},
        {"name": "CI/CD",     "value": len(cicd_list)},
    ]

    # ── MTTR proxy (avg minutes between consecutive incidents) ────────────────
    mttr_display = "N/A"
    if len(incidents) >= 2:
        try:
            sorted_ts = sorted(
                datetime.fromisoformat(i["timestamp"]) for i in incidents
            )
            gaps = [(sorted_ts[j+1] - sorted_ts[j]).total_seconds() / 60
                    for j in range(len(sorted_ts) - 1)]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap < 60:
                mttr_display = f"{int(avg_gap)}m"
            else:
                mttr_display = f"{avg_gap / 60:.1f}h"
        except Exception:
            pass

    return {
        "total_incidents":      total_incidents,
        "critical_alerts":      critical_alerts,
        "unread_notifications": unread_notifs,
        "total_infra":          len(infra_list),
        "total_cicd":           len(cicd_list),
        "mttr":                 mttr_display,
        "incidents_by_severity":incidents_by_severity,
        "top_sources":          top_sources,
        "incidents_over_time":  incidents_over_time,
        "module_activity":      module_activity,
    }


# ── Public health summary (probes, GitHub Actions; no auth) ────────────────────


@app.get("/api/health/summary")
async def api_health_summary():
    from .health import health_checker

    return await health_checker.get_summary()


@app.websocket("/ws/portal")
async def portal_ws(
    websocket: WebSocket,
    user_id: str = Query(default="anonymous"),
):
    from .ws_portal import accept_portal_connection

    await accept_portal_connection(websocket, user_id=user_id)


from .ws_portal import router as ws_portal_router

app.include_router(ws_portal_router)


# TODO: Consider extracting health alert endpoints to routers/health_alerts_api.py
# ── Admin health dashboard API ────────────────────────────────────────────────


@app.get("/api/health/full")
async def api_health_full(_user: User = Depends(require_role("Admin", "User"))):
    from .health import health_checker

    return await health_checker.check_all()


@app.get("/api/health/alerts")
def api_health_alerts(_user: User = Depends(require_role("Admin", "User"))):
    with Session(db_engine) as session:
        rows = session.exec(
            select(HealthAlert)
            .where(HealthAlert.status == "active")
            .order_by(HealthAlert.created_at.desc())
        ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "message": r.message,
            "severity": r.severity,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.post("/api/health/autoheal/all")
async def api_health_autoheal_all(request: Request, _admin: User = Depends(require_admin)):
    from .auto_heal import auto_healer

    results = await auto_healer.heal_all_low_risk()
    write_audit(
        _admin.username,
        _admin.role,
        "health_autoheal",
        resource="/api/health/autoheal/all",
        detail=f"Ran low-risk auto-heal: {len(results)} action(s)",
        ip_address=request.client.host if request.client else "",
    )
    return {"healed": results, "count": len(results)}


@app.post("/api/health/alerts/email")
async def api_health_alerts_email(request: Request, _admin: User = Depends(require_admin)):
    """Queue / record a team email digest for active health alerts (integration hook)."""
    with Session(db_engine) as session:
        rows = session.exec(
            select(HealthAlert).where(HealthAlert.status == "active")
        ).all()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alerts_email",
        resource="/api/health/alerts/email",
        detail=f"Requested alert email digest for {len(rows)} active alert(s)",
        ip_address=request.client.host if request.client else "",
    )
    logger.info("Health alerts email requested", extra={"count": len(rows), "actor": _admin.username})
    return {"ok": True, "queued": len(rows), "message": "Alert digest recorded for team distribution"}


@app.post("/api/health/alerts/{alert_id}/resolve")
def api_health_alert_resolve(
    request: Request,
    alert_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(db_engine) as session:
        row = session.get(HealthAlert, alert_id)
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        detail_snip = (row.message or "")[:200]
        row.status = "resolved"
        session.add(row)
        session.commit()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alert_resolve",
        resource=f"/api/health/alerts/{alert_id}/resolve",
        detail=detail_snip,
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True}


@app.post("/api/health/alerts/{alert_id}/ignore")
def api_health_alert_ignore(
    request: Request,
    alert_id: str,
    _admin: User = Depends(require_admin),
):
    with Session(db_engine) as session:
        row = session.get(HealthAlert, alert_id)
        if not row:
            raise HTTPException(status_code=404, detail="Alert not found")
        detail_snip = (row.message or "")[:200]
        row.status = "ignored"
        session.add(row)
        session.commit()
    write_audit(
        _admin.username,
        _admin.role,
        "health_alert_ignore",
        resource=f"/api/health/alerts/{alert_id}/ignore",
        detail=detail_snip,
        ip_address=request.client.host if request.client else "",
    )
    return {"ok": True}


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "service": "platform-assistant-portal",
    }


# ── Platform Assistant Chatbot ─────────────────────────────────────────────────

CHAT_SYSTEM_TEMPLATE = """You are an SRE Platform Assistant embedded in an AIOps portal.

Current system state:
{context}

Rules:
- Answer ONLY based on the data provided above. Do not invent data.
- Be concise — 2-4 sentences max unless a list is clearly better.
- If the user asks something completely unrelated to platform operations, politely decline.
- Use plain text. No markdown headers, no bullet asterisks.
- If referencing an incident, include its ID and severity.
"""


class ChatRequest(BaseModel):
    message: str


def _build_context() -> str:
    incidents  = get_all_incidents()
    infra_list = get_all_infra()
    cicd_list  = get_all_cicd()
    notifs     = get_all_notifications()

    open_incidents     = [i for i in incidents if i.get("status", "OPEN") == "OPEN"]
    resolved_incidents = [i for i in incidents if i.get("status", "OPEN") == "RESOLVED"]
    critical_open      = [i for i in open_incidents if i["severity"] == "Critical"]

    lines = [
        f"Total incidents: {len(incidents)}",
        f"Open incidents: {len(open_incidents)}",
        f"Resolved incidents: {len(resolved_incidents)}",
        f"Critical open incidents: {len(critical_open)}",
    ]

    if open_incidents:
        lines.append("Open incident summaries:")
        for i in open_incidents[:5]:
            lines.append(f"  - Incident #{i['id']} [{i['severity']}]: {i['summary'][:120]}")

    if resolved_incidents:
        lines.append("Last resolved incidents:")
        for i in resolved_incidents[:3]:
            lines.append(f"  - Incident #{i['id']} [{i['severity']}]: {i['summary'][:100]} (RESOLVED)")

    lines.append(f"Infra generations in DB: {len(infra_list)}")
    if infra_list:
        last_infra = infra_list[0]
        lines.append(f"  Last: {last_infra['resource_name']} on {last_infra['provider_used']}")

    lines.append(f"CI/CD pipelines in DB: {len(cicd_list)}")
    if cicd_list:
        last_cicd = cicd_list[0]
        lines.append(f"  Last: {last_cicd['tool_name']} pipeline")

    unread = sum(1 for n in notifs if not n["is_read"])
    lines.append(f"Unread notifications: {unread}")

    return "\n".join(lines)


@app.post("/api/chat")
@limiter.limit("5/minute")
async def platform_chat(request: Request, chat_in: ChatRequest, current_user: User = Depends(get_current_user)):
    if not chat_in.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    context     = _build_context()
    system_prompt = CHAT_SYSTEM_TEMPLATE.format(context=context)

    try:
        if AI_PROVIDER == "ollama":
            response = await call_ollama(chat_in.message, system_prompt=system_prompt)
        else:
            response = await call_gemini(chat_in.message, system_prompt=system_prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    return {"response": response.strip()}


@app.get("/api/search")
def unified_search(
    q: str = "",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """Search across catalog entities, incidents, tools, cicd, infra."""
    if not q.strip() or len(q.strip()) < 2:
        return []

    term = f"%{q.strip().lower()}%"
    results = []

    with Session(db_engine) as session:
        # Catalog entities
        try:
            from .routers.catalog import CatalogEntity

            cats = session.exec(
                select(CatalogEntity)
                .where(
                    CatalogEntity.is_active == 1,
                    sa_text(
                        "LOWER(name) LIKE :t OR LOWER(owner_team) LIKE :t OR LOWER(COALESCE(description, '')) LIKE :t"
                    ),
                )
                .limit(5),
                {"t": term},
            ).all()
            for c in cats:
                results.append(
                    {
                        "type": "Catalog",
                        "id": c.id,
                        "title": c.name,
                        "subtitle": f"{c.kind} · {c.owner_team}",
                        "url": "/catalog",
                    }
                )
        except Exception:
            pass

        # Incidents
        incidents_all = get_all_incidents()
        for i in incidents_all:
            if term.strip("%") in (i.get("summary") or "").lower() or term.strip("%") in (
                i.get("root_cause") or ""
            ).lower():
                results.append(
                    {
                        "type": "Incident",
                        "id": str(i["id"]),
                        "title": (i.get("summary") or "")[:80],
                        "subtitle": f"{i.get('severity', '?')} · {i.get('status', '?')}",
                        "url": "/incidents",
                    }
                )
                if len(results) >= limit:
                    break

        # Tools
        tools = session.exec(
            select(Tool).where(sa_text("LOWER(name) LIKE :t OR LOWER(category) LIKE :t")).limit(5),
            {"t": term},
        ).all()
        for t_row in tools:
            results.append(
                {
                    "type": "Tool",
                    "id": t_row.id,
                    "title": t_row.name,
                    "subtitle": t_row.category,
                    "url": "/tools",
                }
            )

        # Infra
        infra_all = get_all_infra()
        for item in infra_all:
            if term.strip("%") in (item.get("resource_name") or "").lower():
                results.append(
                    {
                        "type": "Infra",
                        "id": str(item.get("id", "")),
                        "title": (item.get("resource_name") or "")[:60],
                        "subtitle": item.get("provider_used", ""),
                        "url": "/infra",
                    }
                )

        # CI/CD
        cicd_all = get_all_cicd()
        for item in cicd_all:
            if term.strip("%") in (item.get("tool_name") or "").lower():
                results.append(
                    {
                        "type": "CI/CD",
                        "id": str(item.get("id", "")),
                        "title": item.get("tool_name", ""),
                        "subtitle": (item.get("prompt") or "")[:60],
                        "url": "/cicd",
                    }
                )

    return results[:limit]


# ── Log Anomaly Detection ─────────────────────────────────────────────────────

ANOMALY_INCIDENT = {
    "severity":        "Warning",
    "summary":         "Predictive Anomaly: Gradual Memory Leak in auth-service",
    "root_cause":      "auth-service memory usage is increasing by ~5% every hour despite flat request traffic. "
                       "A slow object-reference leak in the session cache layer is the most likely cause.",
    "evidence":        [
        "auth-service RSS: 210 MB → 315 MB over 6 hours (flat traffic)",
        "GC pause frequency up 3× in the last 2 hours",
        "No corresponding spike in active sessions or request rate",
        "Heap dump shows accumulation in SessionCacheManager.activeTokens map",
    ],
    "action_plan":     [
        "1. Capture a heap dump immediately: kill -s SIGUSR1 <pid>",
        "2. Increase JVM -XX:MaxHeapSize as a short-term buffer",
        "3. Rolling restart of auth-service pods to clear current leak",
        "4. Pin SessionCacheManager.activeTokens with a TTL eviction policy",
        "5. Deploy fix and monitor for 2 hours before declaring stable",
    ],
    "commands":        [
        "kubectl top pods -n auth --sort-by=memory",
        "kubectl exec -it auth-service-<pod> -- kill -s SIGUSR1 1",
        "kubectl rollout restart deployment/auth-service -n auth",
        "kubectl logs -f deployment/auth-service -n auth | grep -i 'cache\\|leak\\|OOM'",
    ],
    "files_to_check":  [
        "src/auth/cache/SessionCacheManager.java",
        "k8s/auth-service/deployment.yaml  (resource limits)",
        "config/auth/cache-config.properties",
    ],
    "validation_steps": [
        "Memory growth should plateau within 15 min of rolling restart",
        "GC pause frequency should return to baseline (<5 pauses/min)",
        "Re-run heap dump after 1 hour; activeTokens map should be stable",
    ],
    "raw_logs":        "[anomaly-scanner] Predictive analysis triggered by background log scan.",
    "model_used":      "Anomaly Scanner v1.0 (rule-based)",
    "raw_response":    "",
    "source":          "anomaly-scanner",
}


@app.post("/api/logs/scan-anomalies")
@limiter.limit("5/minute")
async def scan_anomalies(request: Request, current_user: User = Depends(get_current_user)):
    """Simulate a background log scan and create a predictive WARNING incident."""
    if not _demo_data_enabled():
        return {
            "status": "no_data",
            "message": "Anomaly scanner requires demo mode or a real log source.",
        }

    await asyncio.sleep(3)

    record = save_incident(ANOMALY_INCIDENT)
    asyncio.create_task(_hitl_evaluate(
        record.id,
        ANOMALY_INCIDENT["severity"],
        {
            "action_plan": ANOMALY_INCIDENT["action_plan"],
            "commands":    ANOMALY_INCIDENT["commands"],
        },
        ANOMALY_INCIDENT.get("owner_role", "Admin"),
        ANOMALY_INCIDENT.get("source", "anomaly-scanner"),
    ))

    create_notification(
        message="⚠️ Predictive anomaly detected: Gradual memory leak in auth-service (ETA to OOM: 4 h)",
        type="warning",
        incident_id=record.id,
    )

    return serialize_incident(record)


# ── CI/CD Active Monitoring & DORA Metrics ────────────────────────────────────

def _demo_data_enabled() -> bool:
    flag = (os.getenv("ENABLE_DEMO_DATA") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    from .context import PlatformContext

    return PlatformContext.is_dev_environment()


_CICD_ACTIVE_RUNS = [
    {
        "id": "run-a1b2",
        "repository": "platform/auth-service",
        "branch": "main",
        "trigger_user": "rohit.k",
        "trigger_event": "push",
        "commit": "a3f91bc",
        "commit_message": "fix: token refresh race condition",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Test",
        "status": "running",
        "elapsed_time": "3m 12s",
        "stage_statuses": {"Build": "success", "Test": "running", "Security Scan": "pending", "Deploy": "pending"},
    },
    {
        "id": "run-c3d4",
        "repository": "platform/api-gateway",
        "branch": "feature/rate-limiting",
        "trigger_user": "priya.m",
        "trigger_event": "pull_request",
        "commit": "d7e22fa",
        "commit_message": "feat: per-endpoint rate limiting",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Security Scan",
        "status": "running",
        "elapsed_time": "8m 44s",
        "stage_statuses": {"Build": "success", "Test": "success", "Security Scan": "running", "Deploy": "pending"},
    },
    {
        "id": "run-e5f6",
        "repository": "platform/data-ingestion",
        "branch": "feature/v2-refactor",
        "trigger_user": "james.t",
        "trigger_event": "push",
        "commit": "c14a3b2",
        "commit_message": "refactor: switch to async queue",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Test",
        "status": "failed",
        "elapsed_time": "5m 01s",
        "stage_statuses": {"Build": "success", "Test": "failed", "Security Scan": "pending", "Deploy": "pending"},
    },
    {
        "id": "run-g7h8",
        "repository": "platform/frontend-web",
        "branch": "release/2026-q2",
        "trigger_user": "ci-bot",
        "trigger_event": "schedule",
        "commit": "f80d91e",
        "commit_message": "chore: bump dependency versions",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Deploy",
        "status": "running",
        "elapsed_time": "11m 22s",
        "stage_statuses": {"Build": "success", "Test": "success", "Security Scan": "success", "Deploy": "running"},
    },
    {
        "id": "run-i9j0",
        "repository": "platform/ml-inference",
        "branch": "main",
        "trigger_user": "ana.v",
        "trigger_event": "push",
        "commit": "b55aec1",
        "commit_message": "perf: model quantisation",
        "stages": ["Build", "Test", "Security Scan", "Deploy"],
        "current_stage": "Deploy",
        "status": "success",
        "elapsed_time": "14m 05s",
        "stage_statuses": {"Build": "success", "Test": "success", "Security Scan": "success", "Deploy": "success"},
    },
]

_DORA_METRICS = {
    "deployment_frequency": {
        "value": "14 per day",
        "level": "Elite",
        "trend": "+2 vs last week",
        "trend_dir": "up",
    },
    "lead_time": {
        "value": "45 mins",
        "level": "Elite",
        "trend": "-8 min vs last week",
        "trend_dir": "down_good",
    },
    "change_failure_rate": {
        "value": "2.4%",
        "level": "Elite",
        "trend": "-0.3% vs last week",
        "trend_dir": "down_good",
    },
    "mttr": {
        "value": "12 mins",
        "level": "Elite",
        "trend": "-4 min vs last week",
        "trend_dir": "down_good",
    },
}

# Stage → owner role for HITL routing
_CICD_STAGE_ROLES: dict[str, str] = {
    "Build":         "Developer",
    "Lint":          "Developer",
    "Test":          "Developer",
    "Unit Test":     "Developer",
    "Security Scan": "NetworkEngineer",
    "SAST":          "NetworkEngineer",
    "Deploy":        "Developer",
    "Release":       "Developer",
}

# Monitor scenarios
_CICD_MONITOR_SCENARIOS = [
    {
        "stage":      "Security Scan",
        "service":    "api-gateway",
        "severity":   "High",
        "title":      "CI/CD Alert: Security Scan failed — CVE detected in api-gateway",
        "summary":    "CVE-2026-4127 (CVSS 8.9) detected in api-gateway:log4j-core:2.17.0 during Security Scan stage. Immediate patching required.",
        "action_plan":["Update log4j-core to >= 2.23.1", "Re-run SAST scan to confirm remediation", "Merge security patch to release branch"],
        "commands":   ["mvn versions:set-property -Dproperty=log4j.version -DnewVersion=2.23.1", "mvn dependency-check:check"],
        "owner_role": "NetworkEngineer",
    },
    {
        "stage":      "Test",
        "service":    "auth-service",
        "severity":   "Medium",
        "title":      "CI/CD Alert: Flaky tests detected — auth-service integration suite",
        "summary":    "3 of 47 integration tests failed intermittently in auth-service CI. Tests: TokenRefreshTest, SessionExpiry, ConcurrentLoginTest.",
        "action_plan":["Isolate flaky tests and run in --retry mode", "Add test retries for async timing issues", "Pin external mock server version"],
        "commands":   ["pytest tests/integration -k 'TokenRefresh or SessionExpiry' --reruns 3", "git blame tests/integration/test_auth.py"],
        "owner_role": "Developer",
    },
    {
        "stage":      "Deploy",
        "service":    "data-ingestion",
        "severity":   "High",
        "title":      "CI/CD Alert: Deployment rollback required — data-ingestion v3.1.0",
        "summary":    "data-ingestion v3.1.0 deployment to production failed health check after 3 minutes. P99 latency jumped from 120ms to 4.2s. Automatic rollback triggered.",
        "action_plan":["Rollback to v3.0.9 via ArgoCD", "Investigate latency regression in async queue implementation", "Run load test against staging before re-deploying"],
        "commands":   ["argocd app rollback data-ingestion", "kubectl rollout history deployment/data-ingestion -n production"],
        "owner_role": "Developer",
    },
]


@app.get("/api/cicd/active-runs")
def get_cicd_active_runs(current_user: User = Depends(get_current_user)):
    """Return list of currently executing CI/CD pipeline runs."""
    if not _demo_data_enabled():
        return {
            "status": "no_data",
            "runs": [],
            "message": "Connect a GitHub or GitLab CI account to populate active runs.",
        }
    return _CICD_ACTIVE_RUNS


@app.get("/api/cicd/dora-metrics")
def get_dora_metrics(current_user: User = Depends(get_current_user)):
    """Return DORA metrics for the organisation."""
    if not _demo_data_enabled():
        return {
            "status": "no_data",
            "message": "Connect CI/CD tools to compute real DORA metrics.",
            "deployment_frequency": None,
            "lead_time_for_changes": None,
            "change_failure_rate": None,
            "time_to_restore": None,
        }
    return _DORA_METRICS


@app.post("/api/cicd/monitor", status_code=202)
@limiter.limit("5/minute")
async def trigger_cicd_monitor(request: Request, current_user: User = Depends(get_current_user)):
    """Dispatch the CI/CD monitor Celery task (or in-process fallback)."""
    from .tasks import monitor_cicd_pipelines as _monitor_task
    try:
        task = _monitor_task.delay()
        return {"status": "accepted", "task_id": task.id, "message": "CI/CD monitor scan dispatched."}
    except Exception:
        asyncio.create_task(_cicd_monitor_fallback())
        return {"status": "accepted", "task_id": "local-fallback", "message": "CI/CD monitor scan running in-process."}


async def _cicd_monitor_fallback():
    """In-process fallback for monitor when Redis/Celery is unavailable."""
    if not _demo_data_enabled():
        logger.info("CI/CD monitor fallback skipped — demo data disabled")
        return
    import random as _rand
    await asyncio.sleep(2)
    scenario = _rand.choice(_CICD_MONITOR_SCENARIOS)
    record = save_incident({
        "summary":    scenario["title"],
        "severity":   scenario["severity"],
        "root_cause": f"CI/CD monitor detected a failure in the {scenario['stage']} stage. {scenario['summary']}",
        "action_plan": scenario["action_plan"],
        "commands":   scenario["commands"],
        "evidence":   [f"Pipeline stage: {scenario['stage']}", f"Service: {scenario['service']}"],
        "status":     "OPEN",
        "source":     "cicd-monitor",
        "owner_role": scenario["owner_role"],
    })
    create_notification(
        message=f"🔴 CI/CD Monitor: {scenario['title']}",
        type="critical" if scenario["severity"] == "High" else "warning",
        incident_id=record.id,
    )
    parsed = {"summary": scenario["summary"], "action_plan": scenario["action_plan"], "commands": scenario["commands"]}
    asyncio.create_task(_hitl_evaluate(record.id, scenario["severity"], parsed, scenario["owner_role"], scenario["source"]))


# ── DB Query Analyzer ──────────────────────────────────────────────────────────

class QueryAnalyzeRequest(BaseModel):
    query:    str
    database: str = "prod-postgres-primary"


_QUERY_ANALYZER_PROMPT = """You are a senior PostgreSQL and database performance expert.
Analyze the following SQL query and return ONLY a valid JSON object with these exact keys:
{
  "is_valid": true or false,
  "issues": ["list of problems found, or empty array"],
  "index_recommendations": ["list of CREATE INDEX suggestions, or empty array"],
  "estimated_cost": "a human-readable estimate like 'Low', 'Medium', 'High', or 'Very High'",
  "rewritten_query": "an optimized version of the query, or null if already optimal",
  "explain_plan": ["list of 4-6 mock EXPLAIN ANALYZE output lines as strings"],
  "summary": "one sentence plain-English explanation of what the query does and its main performance concern"
}
Return ONLY the JSON. No markdown, no code fences, no explanation."""


@app.post("/api/db/analyze-query")
@limiter.limit("5/minute")
async def analyze_query(request: Request, req: QueryAnalyzeRequest, current_user: User = Depends(get_current_user)):
    """AI-powered SQL query analysis: EXPLAIN plan, index recommendations, rewrite suggestions."""
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty.")

    prompt = f"Database: {req.database}\n\nSQL Query:\n{req.query}\n\n{_QUERY_ANALYZER_PROMPT}"

    try:
        raw = await _ask_ai(prompt)
        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        result  = json.loads(cleaned)
    except Exception:
        result = {
            "is_valid": True,
            "issues": ["Could not parse AI response — showing fallback analysis."],
            "index_recommendations": [],
            "estimated_cost": "Unknown",
            "rewritten_query": None,
            "explain_plan": [
                "Seq Scan on <table>  (cost=0.00..1240.00 rows=50000 width=80)",
                "  Filter: (condition)",
                "Planning Time: 0.8 ms",
                "Execution Time: 342.1 ms",
            ],
            "summary": "Unable to perform AI analysis. Please check your AI provider configuration.",
        }
    return result
