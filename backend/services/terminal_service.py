"""Terminal helpers: history, completion, agent aliases, Redis approval pub/sub."""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlmodel import Session, col, select

from ..agents import AGENT_REGISTRY, list_agents
from ..context import DEFAULT_TENANT_ID, PlatformContext
from ..db.core import engine
from ..db.models.ai_models import AgentRun
from ..db.models.terminal import TerminalApproval, TerminalHistory

logger = logging.getLogger(__name__)

HISTORY_CAP = 100
SESSION_TTL_S = 300
APPROVALS_CHANNEL = "workflow:approvals"
DECISIONS_CHANNEL = "workflow:approvals:decision"

AGENT_ALIASES = {
    "incident": "incident_agent",
    "security": "security_agent",
    "cost": "cost_agent",
    "deploy": "deploy_agent",
    "heal": "auto_heal_agent",
    "catalog": "catalog_health_agent",
    "test": "tester_agent",
    "review": "code_review_agent",
    "docs": "documentation_agent",
    "infra": "infra_agent",
    "runbook": "runbook_agent",
    "pipeline": "pipeline_monitor_agent",
    "noise": "alert_noise_agent",
    "scorecard": "scorecard_agent",
    "onboard": "onboarding_agent",
    "migrate": "migration_agent",
    "drift": "dependency_drift_agent",
    "oncall": "oncall_agent",
    "access": "access_agent",
    "change": "change_agent",
    "compliance": "compliance_agent",
    "offboard": "onboarding_agent",
}

KNOWN_BINARIES = ["kubectl", "helm", "terraform", "git", "aws", "npm", "pip"]

SUBCOMMANDS: dict[str, list[str]] = {
    "kubectl": [
        "get",
        "describe",
        "logs",
        "apply",
        "delete",
        "rollout",
        "scale",
        "exec",
        "port-forward",
        "config",
        "top",
        "api-resources",
    ],
    "helm": ["list", "install", "upgrade", "rollback", "uninstall", "status", "repo", "search"],
    "terraform": ["init", "plan", "apply", "destroy", "validate", "fmt", "state", "output"],
    "git": ["status", "log", "diff", "add", "commit", "push", "pull", "checkout", "branch", "clone"],
    "aws": ["s3", "ec2", "eks", "iam", "sts", "logs", "cloudformation"],
    "npm": ["install", "run", "test", "ci", "audit", "ls"],
    "pip": ["install", "list", "freeze", "uninstall", "show"],
}

# In-process fallbacks when Redis is unavailable (tests / local).
_mem_sessions: dict[str, dict[str, Any]] = {}
_mem_decision_waiters: dict[str, list[Callable[[dict], None]]] = {}
_mem_lock = threading.Lock()


def resolve_agent_alias(alias: str) -> Optional[str]:
    key = (alias or "").strip().lower()
    if not key:
        return None
    if key in AGENT_ALIASES:
        return AGENT_ALIASES[key]
    if key in AGENT_REGISTRY:
        return key
    if key.endswith("_agent") and key in AGENT_REGISTRY:
        return key
    # allow bare name without _agent
    candidate = f"{key}_agent"
    if candidate in AGENT_REGISTRY:
        return candidate
    return None


def grounding_ansi(grounding: str) -> str:
    g = (grounding or "none").strip().lower()
    if g == "live":
        return "\x1b[32m[live]\x1b[0m"
    if g == "partial":
        return "\x1b[33m[partial]\x1b[0m"
    if g == "demo":
        return "\x1b[36m[demo]\x1b[0m"
    return "\x1b[31m[no data]\x1b[0m"


def _redis():
    try:
        from ..services.redis_url import redis_url
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


def store_history(*, tenant_id: str, username: str, command: str) -> None:
    cmd = (command or "").strip()
    if not cmd:
        return
    tid = tenant_id or DEFAULT_TENANT_ID
    with Session(engine) as session:
        session.add(
            TerminalHistory(
                id=str(uuid.uuid4()),
                tenant_id=tid,
                username=username,
                command=cmd,
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        rows = session.exec(
            select(TerminalHistory)
            .where(
                TerminalHistory.tenant_id == tid,
                TerminalHistory.username == username,
            )
            .order_by(col(TerminalHistory.created_at).desc())
        ).all()
        if len(rows) > HISTORY_CAP:
            for old in rows[HISTORY_CAP:]:
                session.delete(old)
            session.commit()


def load_history(*, tenant_id: str, username: str, limit: int = 100) -> list[str]:
    tid = tenant_id or DEFAULT_TENANT_ID
    with Session(engine) as session:
        rows = session.exec(
            select(TerminalHistory)
            .where(
                TerminalHistory.tenant_id == tid,
                TerminalHistory.username == username,
            )
            .order_by(col(TerminalHistory.created_at).asc())
            .limit(limit)
        ).all()
        return [r.command for r in rows if r.command]


def save_session_state(session_id: str, payload: dict[str, Any]) -> None:
    if not session_id:
        return
    blob = json.dumps(payload, default=str)
    client = _redis()
    if client is not None:
        try:
            client.setex(f"terminal:session:{session_id}", SESSION_TTL_S, blob)
            return
        except Exception:
            pass
    with _mem_lock:
        _mem_sessions[session_id] = {"payload": payload, "exp": datetime.now(timezone.utc).timestamp() + SESSION_TTL_S}


def load_session_state(session_id: str) -> Optional[dict[str, Any]]:
    if not session_id:
        return None
    client = _redis()
    if client is not None:
        try:
            raw = client.get(f"terminal:session:{session_id}")
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    with _mem_lock:
        row = _mem_sessions.get(session_id)
        if not row:
            return None
        if row["exp"] < datetime.now(timezone.utc).timestamp():
            _mem_sessions.pop(session_id, None)
            return None
        return dict(row["payload"])


def publish_approval_pending(payload: dict[str, Any]) -> None:
    client = _redis()
    if client is not None:
        try:
            client.publish(APPROVALS_CHANNEL, json.dumps(payload, default=str))
        except Exception as exc:
            logger.debug("redis publish pending failed: %s", exc)


def publish_approval_decision(payload: dict[str, Any]) -> None:
    approval_id = str(payload.get("approval_id") or "")
    client = _redis()
    if client is not None:
        try:
            client.publish(DECISIONS_CHANNEL, json.dumps(payload, default=str))
        except Exception as exc:
            logger.debug("redis publish decision failed: %s", exc)
    # Always notify in-process waiters (tests / same-process)
    with _mem_lock:
        waiters = list(_mem_decision_waiters.get(approval_id, []))
    for cb in waiters:
        try:
            cb(payload)
        except Exception:
            pass


def register_decision_waiter(approval_id: str, callback: Callable[[dict], None]) -> Callable[[], None]:
    with _mem_lock:
        _mem_decision_waiters.setdefault(approval_id, []).append(callback)

    def _unregister() -> None:
        with _mem_lock:
            lst = _mem_decision_waiters.get(approval_id) or []
            try:
                lst.remove(callback)
            except ValueError:
                pass

    return _unregister


def create_terminal_approval(
    *,
    tenant_id: str,
    username: str,
    command: str,
    reasons: list[str],
    session_id: str,
) -> TerminalApproval:
    """Create immutable approval + AgentRun so it appears in the approvals queue."""
    now = datetime.now(timezone.utc)
    approval_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    reasons = list(reasons or [])
    with Session(engine) as session:
        run = AgentRun(
            id=run_id,
            agent="terminal",
            status="pending_approval",
            summary=f"Terminal command requires approval: {command[:120]}",
            details_json=json.dumps(
                {
                    "source": "terminal",
                    "terminal_approval_id": approval_id,
                    "session_id": session_id,
                    "command": command,
                    "reasons": reasons,
                },
                default=str,
            ),
            requires_approval=True,
            approval_payload_json=json.dumps(
                {"commands": [command], "source": "terminal", "terminal_approval_id": approval_id},
                default=str,
            ),
            triggered_by=username,
            user_id=username,
            workspace_id="",
            tenant_id=tenant_id or DEFAULT_TENANT_ID,
            environment=PlatformContext.current_env() or "development",
            task=command[:500],
            created_at=now,
            updated_at=now,
        )
        row = TerminalApproval(
            id=approval_id,
            tenant_id=tenant_id or DEFAULT_TENANT_ID,
            username=username,
            command=command,
            reasons_json=json.dumps(reasons, default=str),
            status="pending",
            session_id=session_id,
            agent_run_id=run_id,
            created_at=now,
        )
        session.add(run)
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)

    publish_approval_pending(
        {
            "type": "approval_required",
            "approval_id": approval_id,
            "agent_run_id": run_id,
            "command": command,
            "username": username,
            "tenant_id": tenant_id,
            "reasons": reasons,
            "session_id": session_id,
        }
    )
    return row


def get_terminal_approval(approval_id: str, tenant_id: str) -> Optional[TerminalApproval]:
    with Session(engine) as session:
        row = session.get(TerminalApproval, approval_id)
        if not row or row.tenant_id != tenant_id:
            return None
        session.expunge(row)
        return row


def mark_approval_status(
    approval_id: str,
    *,
    status: str,
    decided_by: str,
    reason: str = "",
) -> Optional[TerminalApproval]:
    """CAS-ish: only pending → approved/denied/cancelled."""
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = session.get(TerminalApproval, approval_id)
        if not row or row.status != "pending":
            return None
        row.status = status
        row.decided_by = decided_by
        row.decision_reason = reason or None
        row.decided_at = now
        session.add(row)
        # Keep AgentRun in sync when decided outside agents router
        if row.agent_run_id:
            run = session.get(AgentRun, row.agent_run_id)
            if run and run.status == "pending_approval":
                if status == "approved":
                    # Leave as pending for claim_agent_run in agents router,
                    # or mark executing if terminal will run it.
                    run.status = "approved_pending_exec"
                elif status == "denied":
                    run.status = "failed"
                    run.summary = f"Rejected by {decided_by}: {reason or run.summary}"
                    run.requires_approval = False
                elif status == "cancelled":
                    run.status = "failed"
                    run.summary = f"Cancelled from terminal by {decided_by}"
                    run.requires_approval = False
                run.updated_at = now
                session.add(run)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def complete_options(
    partial: str,
    *,
    tenant_id: str,
    cwd: str,
) -> list[str]:
    """Tab completion sources in priority order."""
    text = partial or ""
    parts = text.split()
    token = parts[-1] if parts and not text.endswith(" ") else ""
    # If trailing space, complete next arg from empty prefix
    if text.endswith(" ") or not parts:
        token = ""
        bin_name = parts[0] if parts else ""
    else:
        bin_name = parts[0] if len(parts) >= 1 else ""

    options: list[str] = []

    # 1) binaries
    if len(parts) <= 1 and not text.endswith(" "):
        options.extend(b for b in KNOWN_BINARIES if b.startswith(token))

    # 2) subcommands
    if len(parts) >= 1:
        base = parts[0]
        if base in SUBCOMMANDS:
            if len(parts) == 1 and text.endswith(" "):
                options.extend(SUBCOMMANDS[base])
            elif len(parts) == 2 and not text.endswith(" "):
                options.extend(s for s in SUBCOMMANDS[base] if s.startswith(token))

    # 3) catalog services (tenant-scoped)
    try:
        from ..routers.catalog import CatalogEntity

        with Session(engine) as session:
            q = select(CatalogEntity).where(
                CatalogEntity.tenant_id == (tenant_id or DEFAULT_TENANT_ID),
                CatalogEntity.is_active == 1,
            )
            for ent in session.exec(q).all():
                name = (ent.name or "").strip()
                if name and (not token or name.startswith(token) or token in name):
                    options.append(name)
    except Exception:
        pass

    # 4) k8s namespaces if connector configured
    try:
        from ..services.k8s_access import try_k8s_connector_from_context

        ctx = PlatformContext(tenant_id=tenant_id, user_id="terminal", user_role="Admin")
        with Session(engine) as session:
            conn = try_k8s_connector_from_context(ctx, db=session)
        if conn is not None:
            # Best-effort — connectors vary; ignore failures
            maybe = getattr(conn, "list_namespaces", None)
            if callable(maybe):
                import asyncio

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        ns_list = []
                    else:
                        ns_list = loop.run_until_complete(maybe()) or []
                except Exception:
                    ns_list = []
                for ns in ns_list:
                    name = ns if isinstance(ns, str) else (ns.get("name") if isinstance(ns, dict) else None)
                    if name and (not token or str(name).startswith(token)):
                        options.append(str(name))
    except Exception:
        pass

    # 5) file paths in cwd
    try:
        root = Path(cwd or os.getcwd())
        if root.is_dir():
            for p in sorted(root.iterdir()):
                name = p.name + ("/" if p.is_dir() else "")
                if not token or name.startswith(token) or p.name.startswith(token):
                    options.append(name)
    except Exception:
        pass

    # Deduplicate preserve order
    seen: set[str] = set()
    out: list[str] = []
    for o in options:
        if o not in seen:
            seen.add(o)
            out.append(o)
    return out[:50]


def format_agent_list() -> str:
    lines = ["Available agents:"]
    for a in list_agents():
        alias = next((k for k, v in AGENT_ALIASES.items() if v == a["name"]), a["name"])
        lines.append(f"  @{alias:12}  {a['name']} — {a.get('description') or ''}")
    lines.append("Also: @agents  @runs  @help")
    return "\r\n".join(lines)


def format_capabilities_help() -> str:
    """Render the advertised-tools line from the real capability probe instead
    of a hardcoded list — a tool that isn't installed in this deployment is
    shown as unavailable, not advertised as if it works."""
    from .terminal_capabilities import get_capabilities

    caps = get_capabilities()
    parts = []
    for tool in KNOWN_BINARIES:
        entry = caps.get(tool) or {"available": False, "version": None}
        if entry["available"]:
            label = f"{tool} {entry['version']}" if entry["version"] else tool
        else:
            label = f"{tool} (not installed in this deployment)"
        parts.append(label)
    return "Available: " + ", ".join(parts)


def format_agent_help() -> str:
    return (
        "@ syntax — invoke agents without a shell:\r\n"
        "  @incident <task>   @security <task>   @catalog <task>\r\n"
        "  @deploy <task>     @heal <task>       @cost <task>\r\n"
        "  @agents            list agents\r\n"
        "  @runs              last 10 agent runs for you\r\n"
        "  @help              this help\r\n"
        "Write actions still require HITL approval.\r\n"
    )


def recent_runs_for_user(*, tenant_id: str, username: str, limit: int = 10) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(AgentRun)
            .where(
                AgentRun.tenant_id == (tenant_id or DEFAULT_TENANT_ID),
                AgentRun.user_id == username,
            )
            .order_by(col(AgentRun.created_at).desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "agent": r.agent,
                "status": r.status,
                "summary": r.summary,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
