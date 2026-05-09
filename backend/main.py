import os
import re
import json
import asyncio
import time
import ollama
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from sqlmodel import Session
from sqlalchemy import text as sa_text
from database import engine as db_engine
from auth import auth_router, get_current_user, write_audit, User
from auth import seed_default_admin, seed_default_llm_config
from command_validator import CommandValidator
from tasks import process_inbound_webhook, process_webhook_log
from observability.metrics import (
    INCIDENTS_TOTAL, LLM_LATENCY_SECONDS, AGENT_CONFIDENCE,
    GUARDRAIL_BLOCKS_TOTAL, ACTIVE_APPROVALS, make_asgi_app
)
from database import (
    create_db_and_tables,
    save_incident, get_all_incidents, update_incident_status, serialize_incident,
    save_infra,    get_all_infra,
    save_cicd,     get_all_cicd,
    get_settings,  update_settings,
    create_notification, get_all_notifications, mark_notification_read,
    save_webhook_event, update_webhook_event, get_recent_webhook_events,
    get_pending_approvals,
)

load_dotenv()

# ── Provider config ──────────────────────────────────────────────────────────
# Default to Ollama so the backend can boot without cloud credentials.
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

gemini_client = None
if AI_PROVIDER == "gemini":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        # Don't crash the whole API for local/dev usage; fall back to Ollama.
        print("[ai] GEMINI_API_KEY not set — falling back to AI_PROVIDER=ollama")
        AI_PROVIDER = "ollama"
    else:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)

async def _wait_for_db(retries: int = 30, delay: float = 2.0):
    """
    Block startup until the database accepts connections.
    SQLite is always ready immediately; only PostgreSQL needs a retry loop.
    """
    from database import _is_sqlite
    if _is_sqlite:
        print("[db] SQLite mode — skipping readiness wait.")
        return
    for attempt in range(1, retries + 1):
        try:
            with Session(db_engine) as session:
                session.exec(sa_text("SELECT 1"))
            print(f"[db] PostgreSQL ready (attempt {attempt})")
            return
        except Exception as exc:
            print(f"[db] Waiting for database… attempt {attempt}/{retries}: {exc}")
            await asyncio.sleep(delay)
    raise RuntimeError("Database did not become ready in time. Aborting startup.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _wait_for_db()
    create_db_and_tables()
    from sqlmodel import SQLModel
    from database import engine as db_engine_ref
    SQLModel.metadata.create_all(db_engine_ref)
    seed_default_admin()
    seed_default_llm_config()
    yield
    # (cleanup on shutdown goes here if needed)


app = FastAPI(title="AIOps Portal API", version="0.1.0", lifespan=lifespan)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: JSONResponse({"detail": "Rate limit exceeded"}, status_code=429))
app.include_router(auth_router)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://frontend:5173",  # Docker service name
    ],
    allow_origin_regex=r"^http://localhost:517\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
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
class TriageRequest(BaseModel):
    logs: str


class TriageResponse(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    raw: str
    model_used: str


class IncidentSummary(BaseModel):
    id: int
    timestamp: str
    severity: str
    summary: str
    root_cause: str
    evidence: list[str]
    action_plan: list[str]
    commands: list[str]
    files_to_check: list[str]
    validation_steps: list[str]
    model_used: str
    source: str = "manual"
    raw_logs: str = ""
    status: str = "OPEN"
    execution_logs: str | None = None
    owner_role: str = "Admin"
    proposed_remediation_plan: list[str] = []
    agent_execution_logs: str | None = None


# ── JSON parser with fallback ────────────────────────────────────────────────
def parse_json_response(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(0)
    try:
        data = json.loads(cleaned)
        return {
            "severity":         str(data.get("severity", "Unknown")).capitalize(),
            "summary":          str(data.get("summary", "")),
            "root_cause":       str(data.get("root_cause", "")),
            "evidence":         _to_list(data.get("evidence", [])),
            "action_plan":      _to_list(data.get("action_plan", [])),
            "commands":         _to_list(data.get("commands", [])),
            "files_to_check":   _to_list(data.get("files_to_check", [])),
            "validation_steps": _to_list(data.get("validation_steps", [])),
        }
    except (json.JSONDecodeError, ValueError):
        return {
            "severity":         "Unknown",
            "summary":          "Model returned an unstructured response. See raw output.",
            "root_cause":       text[:800],
            "evidence":         [],
            "action_plan":      [],
            "commands":         [],
            "files_to_check":   [],
            "validation_steps": [],
        }


def _to_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


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


# ── Shared triage core ────────────────────────────────────────────────────────

async def _ask_ai(prompt: str) -> str:
    if AI_PROVIDER == "ollama":
        return await call_ollama(prompt)
    return await call_gemini(prompt)

async def _run_triage(log_text: str, source: str = "manual", owner_role: str = "Admin") -> dict:
    """
    Call AI → parse → save incident → notification → Slack.
    Returns the serialised TriageResponse dict (or raises on AI error).
    """
    _start = time.time()
    if AI_PROVIDER == "ollama":
        raw_text  = await call_ollama(log_text)
        model_used = "Ollama / Gemma 3 4B (Local)"
        LLM_LATENCY_SECONDS.labels(provider=AI_PROVIDER).observe(time.time() - _start)
    else:
        raw_text  = await call_gemini(log_text)
        model_used = "Gemma 3 27B (Cloud)"
        LLM_LATENCY_SECONDS.labels(provider=AI_PROVIDER).observe(time.time() - _start)

    parsed = parse_json_response(raw_text)

    record = save_incident({
        **parsed,
        "raw_logs":     log_text,
        "model_used":   model_used,
        "raw_response": raw_text,
        "source":       source,
        "owner_role":   owner_role,
    })
    INCIDENTS_TOTAL.labels(severity=parsed["severity"], source=source, outcome="triaged").inc()

    severity   = parsed["severity"]
    notif_type = "critical" if severity == "Critical" else \
                 "warning"  if severity in ("High", "Medium") else "info"
    notif_msg  = f"[{severity}] {parsed['summary']}"
    if source != "manual":
        notif_msg += f"  •  via webhook: {source.removeprefix('webhook:')}"
    create_notification(message=notif_msg, type=notif_type, incident_id=record.id)

    if severity in ("Critical", "High"):
        settings = get_settings()
        webhook  = settings.get("slack_webhook_url", "").strip()
        if webhook:
            await _send_slack_alert(webhook, severity, parsed["summary"], parsed["root_cause"])

    # Spawn HITL evaluation as a fire-and-forget async task
    asyncio.create_task(_hitl_evaluate(record.id, severity, parsed, owner_role))

    return {
        "id":              record.id,
        "timestamp":       record.timestamp.isoformat(),
        "severity":        parsed["severity"],
        "summary":         parsed["summary"],
        "root_cause":      parsed["root_cause"],
        "evidence":        parsed["evidence"],
        "action_plan":     parsed["action_plan"],
        "commands":        parsed["commands"],
        "files_to_check":  parsed["files_to_check"],
        "validation_steps":parsed["validation_steps"],
        "raw":             raw_text,
        "model_used":      model_used,
    }


# ── HITL Agentic Processor ────────────────────────────────────────────────────

_AUTO_RESOLVE_SEVERITIES = {"Low", "Warning", "Medium"}
_HITL_SEVERITIES         = {"High", "Critical"}

# Sources that should receive DB-specific SQL remediation plans
_DB_SOURCES = {
    "rds", "aws rds", "postgresql", "postgres",
    "mysql", "mongodb", "redis", "clickhouse",
    "elasticsearch", "sqlite",
}

def _build_db_remediation_plan(summary: str, commands: list[str]) -> list[str]:
    """
    Generate a SQL/CLI-first remediation plan for database incidents.
    Keyword-matches the summary to pick the most relevant script set,
    then appends any AI-generated commands.
    """
    s = summary.lower()

    if any(k in s for k in ("deadlock", "blocking", "lock wait", "lock timeout")):
        plan = [
            "-- 1. Identify blocking transactions",
            "SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state\n"
            "  FROM pg_stat_activity\n"
            "  WHERE state != 'idle' AND query_start < now() - interval '30 seconds'\n"
            "  ORDER BY duration DESC;",
            "-- 2. Kill the blocking process (replace <pid> with value from above)",
            "SELECT pg_terminate_backend(<pid>);",
            "-- 3. Verify no remaining locks",
            "SELECT * FROM pg_locks WHERE NOT granted;",
            "-- 4. Review lock-acquisition order in application code to prevent recurrence",
        ]
    elif any(k in s for k in ("connection", "pool exhausted", "too many clients", "max_connections")):
        plan = [
            "-- 1. Check current connection count",
            "SELECT count(*) FROM pg_stat_activity;",
            "-- 2. View connections grouped by state",
            "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;",
            "-- 3. Terminate idle connections older than 10 minutes",
            "SELECT pg_terminate_backend(pid)\n"
            "  FROM pg_stat_activity\n"
            "  WHERE state = 'idle'\n"
            "    AND query_start < now() - interval '10 minutes';",
            "-- 4. Increase max_connections in postgresql.conf (requires restart)",
            "ALTER SYSTEM SET max_connections = 300;  SELECT pg_reload_conf();",
        ]
    elif any(k in s for k in ("slow query", "slow queries", "long-running", "performance")):
        plan = [
            "-- 1. Find slow queries",
            "SELECT pid, now() - query_start AS runtime, query\n"
            "  FROM pg_stat_activity\n"
            "  WHERE state = 'active' AND query_start < now() - interval '5 seconds'\n"
            "  ORDER BY runtime DESC;",
            "-- 2. Explain the slowest query (replace <pid>)",
            "SELECT pg_cancel_backend(<pid>);",
            "-- 3. Check for missing indexes",
            "SELECT schemaname, tablename, attname, n_distinct, correlation\n"
            "  FROM pg_stats WHERE tablename = '<table_name>';",
            "-- 4. Run VACUUM ANALYZE on affected table",
            "VACUUM ANALYZE <table_name>;",
        ]
    elif any(k in s for k in ("replication", "replica lag", "standby")):
        plan = [
            "-- 1. Check replication lag on primary",
            "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,\n"
            "       (sent_lsn - replay_lsn) AS replication_lag\n"
            "  FROM pg_stat_replication;",
            "-- 2. Confirm replica is streaming",
            "SELECT now() - pg_last_xact_replay_timestamp() AS replication_delay;",
            "-- 3. If lag > 60s, consider promoting replica or reducing write load on primary",
            "-- CLI: pg_ctl promote -D /var/lib/postgresql/data",
        ]
    elif any(k in s for k in ("storage", "disk", "space", "capacity")):
        plan = [
            "-- 1. Check table sizes",
            "SELECT relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS size\n"
            "  FROM pg_catalog.pg_statio_user_tables\n"
            "  ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;",
            "-- 2. Check dead tuple bloat",
            "SELECT relname, n_dead_tup, last_vacuum FROM pg_stat_user_tables\n"
            "  ORDER BY n_dead_tup DESC LIMIT 10;",
            "-- 3. Reclaim space with VACUUM FULL (locks table — run during maintenance window)",
            "VACUUM FULL ANALYZE <table_name>;",
            "-- 4. Archive or partition old data if table > 50 GB",
        ]
    elif any(k in s for k in ("oom", "out of memory", "memory")):
        plan = [
            "-- 1. Check current memory settings",
            "SHOW work_mem;  SHOW shared_buffers;",
            "-- 2. Identify memory-heavy queries",
            "SELECT pid, query, (now() - query_start) AS runtime\n"
            "  FROM pg_stat_activity WHERE state = 'active' ORDER BY runtime DESC;",
            "-- CLI 3. Restart DB process to clear memory (last resort)",
            "sudo systemctl restart postgresql",
        ]
    else:
        # Generic DB fallback
        plan = [
            "-- 1. Check database health",
            "SELECT datname, numbackends, xact_commit, xact_rollback, blks_hit, blks_read\n"
            "  FROM pg_stat_database ORDER BY numbackends DESC;",
            "-- 2. Look for errors in the DB log",
            "sudo tail -n 100 /var/log/postgresql/postgresql-$(date +%Y-%m-%d).log | grep -i error",
            "-- 3. Verify connectivity",
            "psql -U postgres -c 'SELECT version();'",
        ]

    # Append any AI-generated commands that aren't already covered
    for cmd in commands[:3]:
        c = cmd.strip()
        if c and c not in plan:
            plan.append(f"-- AI suggested: {c}")

    return plan

_AGENT_AUTO_LOGS_TEMPLATE = """\
[AGENT] Auto-remediation triggered for Incident #{id} (severity: {severity})
[00:01] Evaluating incident context and action plan...
[00:02] Connecting to target environment...
[00:03] Executing step 1/{total}: {step1}
[00:05] Executing step 2/{total}: {step2}
[00:07] Executing step 3/{total}: {step3}
[00:09] Running post-remediation health checks...
[00:10] Health checks PASSED. Services responding normally.
[00:10] ✅ Incident #{id} auto-resolved by agent. No human intervention required.
"""

async def _hitl_evaluate(incident_id: int, severity: str, parsed: dict, owner_role: str):
    """
    Autonomous path        → LOW / WARNING / MEDIUM : auto-simulate fix → RESOLVED_BY_AGENT
    HITL path              → HIGH / CRITICAL        : set AWAITING_APPROVAL + notify
    Safety guardrail fired → any severity           : ESCALATED_SECURITY_RISK + clear plan
    """
    import json as _json
    await asyncio.sleep(2)   # simulate agent thinking delay

    action_plan = parsed.get("action_plan", []) or []
    commands    = parsed.get("commands",    []) or []

    # ── Safety guardrail: scan raw AI commands before building any plan ────────
    raw_check = CommandValidator.validate(commands + action_plan)
    if not raw_check.safe:
        _escalate_security_risk(incident_id, raw_check.violations, stage="raw AI output")
        return

    if severity in _HITL_SEVERITIES:
        # DB incidents get a SQL/CLI-first remediation plan
        if owner_role == "DatabaseDeveloper":
            plan = _build_db_remediation_plan(
                summary=parsed.get("summary", ""),
                commands=commands,
            )
        else:
            plan = action_plan + (
                [f"Run: {c}" for c in commands[:3]] if commands else []
            )
            if not plan:
                plan = [
                    "1. Isolate the affected service from load balancer",
                    "2. Capture diagnostic snapshot (heap dump / packet trace)",
                    "3. Apply hot-fix and perform rolling restart",
                    "4. Validate with smoke tests before re-routing traffic",
                ]

        # ── Safety guardrail: re-scan the final plan before queuing ───────────
        plan_check = CommandValidator.validate(plan)
        if not plan_check.safe:
            _escalate_security_risk(incident_id, plan_check.violations, stage="final plan")
            return

        update_incident_status(
            incident_id,
            status="AWAITING_APPROVAL",
            proposed_remediation_plan=_json.dumps(plan),
        )
        ACTIVE_APPROVALS.inc()
        create_notification(
            message=f"🤖 Agent requires approval for Incident #{incident_id} [{severity}] — awaiting {owner_role}",
            type="critical" if severity == "Critical" else "warning",
            incident_id=incident_id,
        )
        # Mock outbound Slack alert to owner team
        await _mock_hitl_slack_notify(incident_id, severity, owner_role, parsed.get("summary", ""))
        print(f"[HITL] Incident #{incident_id} → AWAITING_APPROVAL (owner: {owner_role})")

    else:
        # Auto-resolve
        steps  = action_plan if action_plan else ["Restarting service", "Clearing cache", "Verifying health"]
        logs   = _AGENT_AUTO_LOGS_TEMPLATE.format(
            id=incident_id, severity=severity,
            total=min(len(steps), 3),
            step1=steps[0] if len(steps) > 0 else "Restarting affected service",
            step2=steps[1] if len(steps) > 1 else "Clearing stale cache entries",
            step3=steps[2] if len(steps) > 2 else "Running health checks",
        )
        update_incident_status(
            incident_id,
            status="RESOLVED_BY_AGENT",
            agent_execution_logs=logs,
        )
        ACTIVE_APPROVALS.dec()
        create_notification(
            message=f"🤖 Agent auto-resolved Incident #{incident_id} [{severity}] — no approval needed",
            type="info",
            incident_id=incident_id,
        )
        print(f"[HITL] Incident #{incident_id} → RESOLVED_BY_AGENT (autonomous, severity: {severity})")


def _escalate_security_risk(incident_id: int, violations: list[str], stage: str = ""):
    """
    Called when the CommandValidator fires a blocklist hit.
    Updates the incident to ESCALATED_SECURITY_RISK and clears the plan.
    """
    violation_summary = "; ".join(violations[:3])
    print(f"[GUARDRAIL] 🚨 Incident #{incident_id} ESCALATED_SECURITY_RISK — "
          f"blocklist hit at {stage}: {violation_summary}")
    GUARDRAIL_BLOCKS_TOTAL.labels(violation_type=violations[0] if violations else "unknown").inc()
    update_incident_status(
        incident_id,
        status="ESCALATED_SECURITY_RISK",
        proposed_remediation_plan=None,
        agent_execution_logs=(
            f"[GUARDRAIL] AI Safety Guardrail triggered at stage: {stage}\n"
            f"[GUARDRAIL] Violations detected:\n"
            + "\n".join(f"  • {v}" for v in violations)
            + "\n[GUARDRAIL] Proposed plan has been cleared. Manual intervention required."
        ),
    )
    create_notification(
        message=(
            f"🚨 AI Safety Guardrail fired on Incident #{incident_id} — "
            f"destructive command detected. Manual intervention required."
        ),
        type="critical",
        incident_id=incident_id,
    )


async def _mock_hitl_slack_notify(incident_id: int, severity: str, owner_role: str, summary: str):
    """Mock outbound Slack notification to the owner role's channel."""
    try:
        settings = get_settings()
        webhook  = settings.get("slack_webhook_url", "").strip()
        if not webhook:
            print(f"[HITL-Slack] No webhook configured — skipping Slack notify for #{incident_id}")
            return
        payload = {
            "attachments": [{
                "color": "#FF0000" if severity == "Critical" else "#FFA500",
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": f"🤖 HITL Approval Required — {severity} Incident"}},
                    {"type": "section", "fields": [
                        {"type": "mrkdwn", "text": f"*Incident:* #{incident_id}"},
                        {"type": "mrkdwn", "text": f"*Assigned Role:* {owner_role}"},
                        {"type": "mrkdwn", "text": f"*Summary:*\n{summary[:300]}"},
                    ]},
                    {"type": "section", "text": {"type": "mrkdwn",
                        "text": "👉 Open the AIOps portal → *Agent Pending Approvals* to approve or reject."}},
                ],
            }]
        }
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(webhook, json=payload)
    except Exception as exc:
        print(f"[HITL-Slack] notify failed: {exc}")


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/triage", response_model=TriageResponse)
async def triage_logs(request: TriageRequest, current_user: User = Depends(get_current_user)):
    if not request.logs.strip():
        raise HTTPException(status_code=400, detail="Log text cannot be empty.")
    try:
        result = await _run_triage(request.logs, source="manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")
    return TriageResponse(**result)


@app.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents(role: str | None = None, current_user: User = Depends(get_current_user)):
    """Return all incidents. If ?role=<X> is provided and role != Admin,
    only incidents where owner_role matches are returned."""
    incidents = get_all_incidents()
    if role and role != "Admin":
        incidents = [i for i in incidents if i.get("owner_role", "Admin") == role]
    return incidents


MOCK_RUNBOOK_LOGS = """\
[00:00] Initializing Automated Runbook...
[00:01] Authenticating with target cluster...
[00:02] Connecting to target nodes: node-01, node-02, node-03
[00:03] Running pre-flight health checks... OK
[00:04] Identifying affected services from incident metadata...
[00:05] Executing remediation step 1/4: Draining affected pods...
[00:06] Executing remediation step 2/4: Restarting failed services...
[00:07] Executing remediation step 3/4: Clearing stale locks and cache entries...
[00:08] Executing remediation step 4/4: Verifying service health endpoints...
[00:09] All health checks passed. Services are responding normally.
[00:10] Rolling back temporary network policy overrides...
[00:11] Emitting resolution event to monitoring platform...
[00:12] Incident successfully mitigated. Status set to RESOLVED."""


@app.post("/api/incidents/{incident_id}/remediate")
async def remediate_incident(incident_id: int, current_user: User = Depends(get_current_user)):
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") == "RESOLVED":
        raise HTTPException(status_code=400, detail="Incident is already resolved")

    # Simulate execution delay
    await asyncio.sleep(2)

    updated = update_incident_status(
        incident_id,
        status="RESOLVED",
        execution_logs=MOCK_RUNBOOK_LOGS,
    )

    create_notification(
        message=f"✅ Incident #{incident_id} auto-remediated via Automated Runbook",
        type="info",
        incident_id=incident_id,
    )

    return updated


# ── HITL Approval / Rejection routes ─────────────────────────────────────────

_SERVICENOW_MOCK_URL = "https://mock-servicenow.internal/api/incidents/close"

_AGENT_APPROVED_LOGS = """\
[AGENT] Approval received from {role}. Beginning execution of Incident #{id}...
[00:01] Verifying approval token and incident context...
[00:02] Connecting to target cluster and validating credentials...
[00:03] Step 1 — {step1}
[00:05] Step 2 — {step2}
[00:07] Step 3 — {step3}
[00:08] Executing post-remediation validation suite...
[00:09] All health checks PASSED ✓
[00:10] ✅ Incident #{id} resolved by agent following human approval.
[00:10] ServiceNow ticket closure webhook fired → {sn_url}
"""


class ApprovalRequest(BaseModel):
    approved_by_role: str = "Admin"


@app.post("/api/incidents/{incident_id}/approve")
async def approve_incident(incident_id: int, body: ApprovalRequest, current_user: User = Depends(get_current_user)):
    import json as _json
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    plan  = incident.get("proposed_remediation_plan") or []
    steps = plan if isinstance(plan, list) else []

    await asyncio.sleep(3)   # simulate execution

    logs = _AGENT_APPROVED_LOGS.format(
        role=current_user.role,
        id=incident_id,
        step1=steps[0] if len(steps) > 0 else "Isolating affected service",
        step2=steps[1] if len(steps) > 1 else "Applying remediation patch",
        step3=steps[2] if len(steps) > 2 else "Restarting and validating services",
        sn_url=_SERVICENOW_MOCK_URL,
    )

    updated = update_incident_status(
        incident_id,
        status="RESOLVED_BY_AGENT",
        agent_execution_logs=logs,
    )
    ACTIVE_APPROVALS.dec()
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="APPROVE",
        resource=f"incident:{incident_id}",
        detail="plan approved"
    )

    create_notification(
        message=f"✅ Incident #{incident_id} resolved by agent after approval by {current_user.role}",
        type="info",
        incident_id=incident_id,
    )

    # Fire mock ServiceNow ticket-close webhook (fire-and-forget)
    asyncio.create_task(_close_servicenow_ticket(incident_id))

    return updated


@app.post("/api/incidents/{incident_id}/reject")
async def reject_incident(incident_id: int, current_user: User = Depends(get_current_user)):
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident.get("status") != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail="Incident is not awaiting approval")

    updated = update_incident_status(incident_id, status="REJECTED")
    write_audit(
        actor=current_user.username,
        actor_role=current_user.role,
        event_type="REJECT",
        resource=f"incident:{incident_id}",
        detail="plan rejected"
    )
    create_notification(
        message=f"🚫 Incident #{incident_id} agent execution rejected by operator",
        type="warning",
        incident_id=incident_id,
    )
    return updated


@app.get("/api/incidents/approvals")
def list_pending_approvals(role: str | None = None, current_user: User = Depends(get_current_user)):
    return get_pending_approvals(role=role)


async def _close_servicenow_ticket(incident_id: int):
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(_SERVICENOW_MOCK_URL, json={
                "incident_id": incident_id,
                "action": "close",
                "resolved_by": "AIOps-Agent",
            })
    except Exception as exc:
        print(f"[ServiceNow] mock ticket close for #{incident_id}: {exc}")


# ── Webhook Ingestion ──────────────────────────────────────────────────────────

async def _webhook_background_fallback(log_text: str, source: str):
    """In-process fallback used when Redis/Celery is unavailable (local dev)."""
    try:
        await _run_triage(log_text, source=f"webhook:{source}")
    except Exception as exc:
        print(f"[webhook-fallback] triage failed for source={source}: {exc}")


async def _inbound_webhook_background_fallback(payload: dict, source: str, event_id: int):
    """In-process fallback for the inbound gateway when Redis/Celery is unavailable."""
    try:
        _event_type, log_text, _ = _map_to_cloud_event(payload, source)
        owner_role = _route_owner(source)
        result = await _run_triage(log_text, source=f"webhook:{source}", owner_role=owner_role)
        update_webhook_event(event_id, status="processed", incident_id=result.get("id"))
    except Exception as exc:
        update_webhook_event(event_id, status="error")
        print(f"[webhook-fallback] inbound event {event_id} failed: {exc}")


class WebhookLogRequest(BaseModel):
    source:    str
    log_text:  str
    timestamp: str | None = None


@app.post("/api/webhooks/logs", status_code=202)
async def ingest_webhook_log(request: WebhookLogRequest):
    """Accept a log payload, return 202 immediately, dispatch Celery task for triage."""
    if not request.log_text.strip():
        raise HTTPException(status_code=400, detail="log_text cannot be empty.")
    if not request.source.strip():
        raise HTTPException(status_code=400, detail="source cannot be empty.")

    try:
        task = process_webhook_log.delay(request.log_text, request.source.strip())
        task_id = task.id
    except Exception:
        # Redis not available in local dev — fall back to in-process background task
        asyncio.create_task(_webhook_background_fallback(request.log_text, request.source.strip()))
        task_id = "local-fallback"

    return {
        "status":  "accepted",
        "task_id": task_id,
        "message": f"Log from '{request.source}' queued for triage.",
    }


# ── Webhook Gateway (inbound, auto-routing) ───────────────────────────────────

# Source → owner_role routing table
_ROLE_ROUTES: dict[str, str] = {
    # Developer
    "github":       "Developer",
    "gitlab":       "Developer",
    "jira":         "Developer",
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
    ]
    log_text = next((c for c in candidates if c), None)
    if not log_text:
        log_text = f"Inbound webhook event from {source}:\n{_json.dumps(payload, indent=2)}"

    cloud_event_id = str(uuid.uuid4())
    return str(event_type), log_text, cloud_event_id


class InboundWebhookRequest(BaseModel):
    source:     str
    payload:    dict = {}
    event_type: str | None = None


@app.post("/api/webhooks/inbound", status_code=202)
async def inbound_webhook_gateway(request: InboundWebhookRequest):
    """
    Queue-first webhook gateway.
    Accepts any source+payload, returns 202 immediately,
    dispatches a Celery task for normalization + AI triage.
    """
    import json as _json, uuid
    source = request.source.strip().lower()
    from webhooks.security import require_valid_signature
    raw_body = str(request.payload).encode()
    require_valid_signature(source, raw_body, dict(request.headers) if hasattr(request, "headers") else {})
    if not source:
        raise HTTPException(status_code=400, detail="source cannot be empty.")

    payload    = request.payload or {}
    event_type = request.event_type or _map_to_cloud_event(payload, source)[0]
    owner_role = _route_owner(source)
    ce_id      = str(uuid.uuid4())

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


@app.get("/api/webhooks/activity")
def webhook_activity(limit: int = 40):
    return get_recent_webhook_events(limit=limit)


# ── Slack helper ──────────────────────────────────────────────────────────────

async def _send_slack_alert(webhook: str, severity: str, summary: str, root_cause: str):
    """Fire-and-forget Slack webhook; logs errors but never raises."""
    color = "#FF0000" if severity == "Critical" else "#FFA500"
    payload = {
        "attachments": [{
            "color": color,
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": f"🚨 {severity} Alert — AIOps Portal"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"},
                    {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"},
                ]},
                {"type": "context", "elements": [
                    {"type": "mrkdwn", "text": "Sent by *Platform Engineering Assistant*"}
                ]},
            ],
        }]
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(webhook, json=payload)
            r.raise_for_status()
    except Exception as exc:
        print(f"[Slack] Failed to send alert: {exc}")


# ── Notifications ──────────────────────────────────────────────────────────────

@app.get("/api/notifications")
def fetch_notifications(current_user: User = Depends(get_current_user)):
    return get_all_notifications()


@app.put("/api/notifications/{notification_id}/read")
def read_notification(notification_id: int, current_user: User = Depends(get_current_user)):
    result = mark_notification_read(notification_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return result


# ── Jira Integration ───────────────────────────────────────────────────────────

JIRA_FORMAT_PROMPT = """You are a senior SRE writing a Jira incident ticket.
Given the incident data below, return ONLY a JSON object with these fields:
- "title": concise one-line issue summary (max 100 chars)
- "description": detailed markdown description (2-4 sentences, plain text)
- "steps_to_reproduce": list of strings describing how to reproduce / verify the issue
- "priority": one of "Highest", "High", "Medium", "Low"

Return ONLY raw JSON. No markdown fences.
"""

def _to_adf(text: str) -> dict:
    """Wrap plain text in Atlassian Document Format paragraph."""
    return {
        "version": 1,
        "type": "doc",
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }


@app.post("/api/incidents/{incident_id}/jira")
async def create_jira_ticket(incident_id: int, current_user: User = Depends(get_current_user)):
    # Load incident
    all_incidents = get_all_incidents()
    incident = next((i for i in all_incidents if i["id"] == incident_id), None)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Load Jira settings
    settings = get_settings()
    domain    = settings.get("jira_domain", "").strip()
    email     = settings.get("jira_email", "").strip()
    token     = settings.get("jira_api_token", "").strip()
    proj_key  = settings.get("jira_project_key", "").strip()

    if not all([domain, email, token, proj_key]):
        raise HTTPException(status_code=400, detail="Jira credentials are incomplete. Configure them in Settings.")

    # Ask AI to format the ticket
    incident_summary_text = (
        f"Severity: {incident['severity']}\n"
        f"Summary: {incident['summary']}\n"
        f"Root Cause: {incident['root_cause']}\n"
        f"Action Plan: {'; '.join(incident.get('action_plan', []))}\n"
        f"Commands: {'; '.join(incident.get('commands', []))}"
    )
    prompt = JIRA_FORMAT_PROMPT + "\n\nIncident:\n" + incident_summary_text

    try:
        if AI_PROVIDER == "ollama":
            raw = await call_ollama(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
        else:
            raw = await call_gemini(incident_summary_text, system_prompt=JIRA_FORMAT_PROMPT)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    # Parse AI response
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        jira_data = json.loads(m.group(0)) if m else {}
    except Exception:
        jira_data = {}

    title      = jira_data.get("title", incident["summary"])[:100]
    description = jira_data.get("description", incident["root_cause"])
    steps       = jira_data.get("steps_to_reproduce", [])
    priority    = jira_data.get("priority", "High")

    # Build description ADF with steps
    steps_text = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) if steps else ""
    full_desc   = f"{description}\n\nSteps to Reproduce:\n{steps_text}" if steps_text else description
    adf_body    = _to_adf(full_desc)

    # Call Jira API
    import base64
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {creds}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }
    payload = {
        "fields": {
            "project":     {"key": proj_key},
            "summary":     title,
            "description": adf_body,
            "issuetype":   {"name": "Bug"},
            "priority":    {"name": priority},
        }
    }
    jira_url = f"https://{domain}/rest/api/3/issue"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(jira_url, headers=headers, json=payload)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Jira API error {exc.response.status_code}: {exc.response.text}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Jira connection error: {str(exc)}")

    ticket_key = result.get("key", "UNKNOWN")
    ticket_url = f"https://{domain}/browse/{ticket_key}"

    create_notification(
        message=f"Jira ticket {ticket_key} created for Incident #{incident_id}",
        type="info",
        incident_id=incident_id,
    )

    return {"ticket_key": ticket_key, "ticket_url": ticket_url}


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
async def generate_infra(request: InfraRequest, current_user: User = Depends(get_current_user)):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    provider      = request.provider.strip() or "GCP"
    system_prompt = build_infra_prompt(provider)
    user_msg      = f"Infrastructure request: {request.prompt}"

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
        "prompt":     request.prompt,
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
async def generate_cicd(request: CICDRequest, current_user: User = Depends(get_current_user)):
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty.")

    tool = request.cicd_tool.strip() or "GitHub Actions"
    ctx  = CICD_TOOL_CONTEXT.get(tool, CICD_TOOL_CONTEXT["GitHub Actions"])

    system_prompt = CICD_SYSTEM_PROMPT_TEMPLATE.format(
        tool=tool,
        file=ctx["file"],
        format=ctx["format"],
        syntax_hints=ctx["syntax_hints"],
        stage_pattern=ctx["stage_pattern"],
        example_stages=ctx["example_stages"],
    )
    user_msg = f"Application description: {request.prompt}"

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
        "prompt":     request.prompt,
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
def save_settings(body: dict, current_user: User = Depends(get_current_user)):
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


@app.get("/health")
def health():
    return {"status": "ok", "provider": AI_PROVIDER, "model": OLLAMA_MODEL}


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
async def platform_chat(request: ChatRequest, current_user: User = Depends(get_current_user)):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    context     = _build_context()
    system_prompt = CHAT_SYSTEM_TEMPLATE.format(context=context)

    try:
        if AI_PROVIDER == "ollama":
            response = await call_ollama(request.message, system_prompt=system_prompt)
        else:
            response = await call_gemini(request.message, system_prompt=system_prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    return {"response": response.strip()}


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
async def scan_anomalies(current_user: User = Depends(get_current_user)):
    """Simulate a background log scan and create a predictive WARNING incident."""
    await asyncio.sleep(3)

    record = save_incident(ANOMALY_INCIDENT)

    create_notification(
        message="⚠️ Predictive anomaly detected: Gradual memory leak in auth-service (ETA to OOM: 4 h)",
        type="warning",
        incident_id=record.id,
    )

    return serialize_incident(record)


# ── CI/CD Active Monitoring & DORA Metrics ────────────────────────────────────

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
    return _CICD_ACTIVE_RUNS


@app.get("/api/cicd/dora-metrics")
def get_dora_metrics(current_user: User = Depends(get_current_user)):
    """Return DORA metrics for the organisation."""
    return _DORA_METRICS


@app.post("/api/cicd/monitor", status_code=202)
async def trigger_cicd_monitor(current_user: User = Depends(get_current_user)):
    """Dispatch the CI/CD monitor Celery task (or in-process fallback)."""
    from tasks import monitor_cicd_pipelines as _monitor_task
    try:
        task = _monitor_task.delay()
        return {"status": "accepted", "task_id": task.id, "message": "CI/CD monitor scan dispatched."}
    except Exception:
        asyncio.create_task(_cicd_monitor_fallback())
        return {"status": "accepted", "task_id": "local-fallback", "message": "CI/CD monitor scan running in-process."}


async def _cicd_monitor_fallback():
    """In-process fallback for monitor when Redis/Celery is unavailable."""
    import random as _rand
    await asyncio.sleep(2)
    scenario = _rand.choice(_CICD_MONITOR_SCENARIOS)
    record = save_incident({
        "title":      scenario["title"],
        "severity":   scenario["severity"],
        "summary":    scenario["summary"],
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
        type="critical" if scenario["severity"] == "High" else "warning",
        incident_id=record.id,
    )
    parsed = {"summary": scenario["summary"], "action_plan": scenario["action_plan"], "commands": scenario["commands"]}
    asyncio.create_task(_hitl_evaluate(record.id, scenario["severity"], parsed, scenario["owner_role"]))


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
async def analyze_query(req: QueryAnalyzeRequest, current_user: User = Depends(get_current_user)):
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
