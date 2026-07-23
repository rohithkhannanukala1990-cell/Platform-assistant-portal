"""Triage, HITL, Slack, and remediation helpers."""
import asyncio
import json
import os
import re
import time

import httpx

from ..command_validator import CommandValidator
from ..database import (
    create_notification,
    get_settings,
    save_incident,
    update_incident_status,
    update_webhook_event,
)
from ..observability.logger import logger
from ..observability.metrics import (
    ACTIVE_APPROVALS,
    AGENT_CONFIDENCE,
    GUARDRAIL_BLOCKS_TOTAL,
    INCIDENTS_TOTAL,
    LLM_LATENCY_SECONDS,
)
from ..ai.ai_utils import call_gemini, call_ollama

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()

TRIAGE_SYSTEM_PROMPT = """You are a senior DevOps and SRE engineer embedded inside Cursor IDE.
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
            "evidence":         to_list(data.get("evidence", [])),
            "action_plan":      to_list(data.get("action_plan", [])),
            "commands":         to_list(data.get("commands", [])),
            "files_to_check":   to_list(data.get("files_to_check", [])),
            "validation_steps": to_list(data.get("validation_steps", [])),
            "confidence":       float(data.get("confidence", 0.0)),
            "threat_type":      str(data.get("threat_type", "")),
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


def to_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []

async def run_triage(log_text: str, source: str = "manual", owner_role: str = "Admin") -> dict:
    """
    Call AI → parse → save incident → notification → Slack.
    Returns the serialised TriageResponse dict (or raises on AI error).
    """
    from .agents.security_agent import is_security_source, SECURITY_SYSTEM_PROMPT
    from .agents.tester_agent import is_tester_source, TESTER_SYSTEM_PROMPT
    if is_security_source(source):
        active_system_prompt = SECURITY_SYSTEM_PROMPT
    elif is_tester_source(source):
        active_system_prompt = TESTER_SYSTEM_PROMPT
    else:
        active_system_prompt = TRIAGE_SYSTEM_PROMPT

    _start = time.time()
    if AI_PROVIDER == "ollama":
        raw_text  = await call_ollama(log_text, system_prompt=active_system_prompt)
        model_used = "Ollama / Gemma 3 4B (Local)"
        LLM_LATENCY_SECONDS.labels(provider=AI_PROVIDER).observe(time.time() - _start)
    else:
        raw_text  = await call_gemini(log_text, system_prompt=active_system_prompt)
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
    confidence_val = parsed.get("confidence", 0.0)
    if isinstance(confidence_val, (int, float)) and 0.0 <= confidence_val <= 1.0:
        AGENT_CONFIDENCE.observe(confidence_val)

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
            await send_slack_alert(webhook, severity, parsed["summary"], parsed["root_cause"])

    # Spawn HITL evaluation as a fire-and-forget async task
    asyncio.create_task(hitl_evaluate(record.id, severity, parsed, owner_role, source))

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

def build_db_remediation_plan(summary: str, commands: list[str]) -> list[str]:
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

async def hitl_evaluate(incident_id: int, severity: str, parsed: dict, owner_role: str, source: str = ""):
    """
    Autonomous path        → LOW / WARNING / MEDIUM : auto-simulate fix → RESOLVED_BY_AGENT
    HITL path              → HIGH / CRITICAL        : set AWAITING_APPROVAL + notify
    Safety guardrail fired → any severity           : ESCALATED_SECURITY_RISK + clear plan
    """
    import json as _json
    await asyncio.sleep(2)   # simulate agent thinking delay

    # Security incidents ALWAYS go to HITL regardless of severity
    from .agents.security_agent import is_security_source
    if is_security_source(source):
        severity = "High"  # force HITL for all security events

    action_plan = parsed.get("action_plan", []) or []
    commands    = parsed.get("commands",    []) or []

    # ── Safety guardrail: scan raw AI commands before building any plan ────────
    raw_check = CommandValidator.validate(commands + action_plan)
    if not raw_check.safe:
        escalate_security_risk(incident_id, raw_check.violations, stage="raw AI output")
        return

    if severity in _HITL_SEVERITIES:
        # DB incidents get a SQL/CLI-first remediation plan
        if owner_role == "DatabaseDeveloper":
            plan = build_db_remediation_plan(
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
            escalate_security_risk(incident_id, plan_check.violations, stage="final plan")
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
        await mock_hitl_slack_notify(incident_id, severity, owner_role, parsed.get("summary", ""))
        logger.info("Incident routed to HITL", extra={"incident_id": incident_id, "status": "AWAITING_APPROVAL", "owner_role": owner_role})

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
        create_notification(
            message=f"🤖 Agent auto-resolved Incident #{incident_id} [{severity}] — no approval needed",
            type="info",
            incident_id=incident_id,
        )
        logger.info("Incident auto-resolved by agent", extra={"incident_id": incident_id, "severity": severity})


def escalate_security_risk(incident_id: int, violations: list[str], stage: str = ""):
    """
    Called when the CommandValidator fires a blocklist hit.
    Updates the incident to ESCALATED_SECURITY_RISK and clears the plan.
    """
    violation_summary = "; ".join(violations[:3])
    logger.error("AI Safety Guardrail triggered", extra={"incident_id": incident_id, "violations": violation_summary, "stage": stage})
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


async def mock_hitl_slack_notify(incident_id: int, severity: str, owner_role: str, summary: str):
    """Mock outbound Slack notification to the owner role's channel."""
    try:
        settings = get_settings()
        webhook  = settings.get("slack_webhook_url", "").strip()
        if not webhook:
            logger.info("Slack webhook not configured - skipping HITL notify", extra={"incident_id": incident_id})
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
        logger.error("Slack alert failed", extra={"error": str(exc)})


# TODO: Consider extracting incident-related endpoints to routers/incidents_api.py
# ── Routes ───────────────────────────────────────────────────────────────────

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

_SERVICENOW_MOCK_URL = "https://mock-servicenow.internal/api/incidents/close"

AGENT_APPROVED_LOGS = """\
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

async def close_servicenow_ticket(incident_id: int):
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(_SERVICENOW_MOCK_URL, json={
                "incident_id": incident_id,
                "action": "close",
                "resolved_by": "AIOps-Agent",
            })
    except Exception as exc:
        logger.warning("ServiceNow ticket close failed", extra={"incident_id": incident_id, "error": str(exc)})

async def send_slack_alert(webhook: str, severity: str, summary: str, root_cause: str):
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
        logger.error("Slack alert failed", extra={"error": str(exc)})

def to_adf(text: str) -> dict:
    """Wrap plain text in Atlassian Document Format paragraph."""
    return {
        "version": 1,
        "type": "doc",
        "content": [{
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        }],
    }

# Test / legacy aliases
_run_triage = run_triage
hitl_evaluate = hitl_evaluate
send_slack_alert = send_slack_alert
build_db_remediation_plan = build_db_remediation_plan
