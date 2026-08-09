"""Portal domain tools exposed by the MCP server (Phase M2).

Read tools query portal data. Write tools only create HITL-pending work —
they never execute remediations or mutating agent commands directly.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..context import DEFAULT_TENANT_ID, PlatformContext, resolve_tenant_id
from ..database import AgentRun, engine
from ..db.repositories.incidents import get_incident, list_incidents, update_incident_status
from ..health import health_checker
from ..routers.catalog import CatalogEntity
from ..services.github_access import try_github_connector_from_context
from ..services.isolation import apply_tenant_filter

# ── tool catalog (JSON Schema) ────────────────────────────────────────────────

PORTAL_TOOLS: list[dict[str, Any]] = [
    {
        "name": "portal_list_incidents",
        "description": "List recent portal incidents (tenant-scoped).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "status": {"type": "string"},
                "tenant_id": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_get_incident",
        "description": "Get one incident by id (tenant-scoped).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "integer"},
                "tenant_id": {"type": "string"},
            },
            "required": ["incident_id"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_list_catalog_services",
        "description": "List active catalog services / entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
                "tenant_id": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_search",
        "description": "Search catalog entities by name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "kind": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "tenant_id": {"type": "string"},
            },
            "required": ["q"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_health_summary",
        "description": "Platform health probe summary.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_list_github_repos",
        "description": "List GitHub repositories via the scoped Tool Registry account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "per_page": {"type": "integer", "default": 20},
                "user_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "tenant_id": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "portal_propose_remediation",
        "description": (
            "Propose a remediation plan for an incident (HITL). "
            "Sets status to AWAITING_APPROVAL — does not execute commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "integer"},
                "plan": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ]
                },
                "tenant_id": {"type": "string"},
            },
            "required": ["incident_id", "plan"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
    {
        "name": "portal_run_agent",
        "description": (
            "Queue a portal agent run for human approval (HITL). "
            "Does not execute mutating commands."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent": {"type": "string", "description": "Agent name, e.g. code_review_agent"},
                "task": {"type": "string"},
                "params": {"type": "object"},
                "user_id": {"type": "string"},
                "workspace_id": {"type": "string"},
                "tenant_id": {"type": "string"},
                "environment": {"type": "string", "default": "development"},
            },
            "required": ["agent", "task"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": True},
    },
]

WRITE_TOOLS = {
    "portal_propose_remediation",
    "portal_run_agent",
    "portal_github_create_branch",
    "portal_github_commit_file",
    "portal_github_create_pull_request",
    "portal_github_add_pr_review",
    "portal_jira_create_issue",
    "portal_jira_transition_issue",
    "portal_jira_comment_on_issue",
    "portal_jira_link_issues",
    "portal_slack_post_thread_reply",
    "portal_slack_post_approval_request",
    "portal_slack_update_message",
    "portal_servicenow_create_change_request",
    "portal_servicenow_update_change_state",
    "portal_servicenow_create_incident",
    "portal_confluence_create_page",
    "portal_confluence_update_page",
}


def mcp_enabled() -> bool:
    flag = (os.getenv("MCP_ENABLED") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def _tenant(arguments: dict[str, Any]) -> str:
    return resolve_tenant_id(arguments.get("tenant_id"), DEFAULT_TENANT_ID)


def _ok(payload: Any) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": False,
        "structuredContent": payload if not isinstance(payload, str) else {"text": payload},
    }


def _err(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


async def portal_list_incidents(arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit") or 20)
    status = (arguments.get("status") or None) or None
    rows = list_incidents(limit=limit, status=status, tenant_id=_tenant(arguments))
    return _ok({"incidents": rows, "count": len(rows)})


async def portal_get_incident(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        incident_id = int(arguments["incident_id"])
    except (KeyError, TypeError, ValueError):
        return _err("incident_id is required")
    row = get_incident(incident_id, tenant_id=_tenant(arguments))
    if row is None:
        return _err(f"Incident {incident_id} not found")
    return _ok(row)


async def portal_list_catalog_services(arguments: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _tenant(arguments)
    limit = max(1, min(int(arguments.get("limit") or 50), 200))
    kind = (arguments.get("kind") or "").strip()
    with Session(engine) as session:
        q = select(CatalogEntity).where(CatalogEntity.is_active == 1)
        q = apply_tenant_filter(q, CatalogEntity, tenant_id)
        if kind:
            q = q.where(CatalogEntity.kind == kind)
        rows = session.exec(q.limit(limit)).all()
        services = [
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "lifecycle": r.lifecycle,
                "owner_team": r.owner_team,
                "repo_url": r.repo_url,
                "description": r.description,
                "health_status": r.health_status,
            }
            for r in rows
        ]
    return _ok({"services": services, "count": len(services)})


async def portal_search(arguments: dict[str, Any]) -> dict[str, Any]:
    qtext = (arguments.get("q") or "").strip()
    if not qtext:
        return _err("q is required")
    tenant_id = _tenant(arguments)
    kind = (arguments.get("kind") or "").strip()
    limit = max(1, min(int(arguments.get("limit") or 20), 100))
    pattern = f"%{qtext}%"
    with Session(engine) as session:
        q = select(CatalogEntity).where(
            CatalogEntity.is_active == 1,
            col(CatalogEntity.name).ilike(pattern),
        )
        q = apply_tenant_filter(q, CatalogEntity, tenant_id)
        if kind:
            q = q.where(CatalogEntity.kind == kind)
        rows = session.exec(q.limit(limit)).all()
        results = [
            {
                "id": r.id,
                "name": r.name,
                "kind": r.kind,
                "lifecycle": r.lifecycle,
                "repo_url": r.repo_url,
                "description": r.description,
            }
            for r in rows
        ]
    return _ok({"results": results, "count": len(results), "q": qtext})


async def portal_health_summary(_arguments: dict[str, Any]) -> dict[str, Any]:
    summary = await health_checker.get_summary()
    return _ok(summary)


async def portal_list_github_repos(arguments: dict[str, Any]) -> dict[str, Any]:
    per_page = max(1, min(int(arguments.get("per_page") or 20), 100))
    ctx = PlatformContext(
        user_id=str(arguments.get("user_id") or "mcp"),
        workspace_id=str(arguments.get("workspace_id") or ""),
        tenant_id=_tenant(arguments),
        environment="development",
    )
    with Session(engine) as db:
        connector = try_github_connector_from_context(ctx, db=db)
        if connector is None:
            return _err("GitHub not connected. Connect a GitHub account in Tool Registry.")
        try:
            repos = await connector.list_repos(per_page=per_page)
        except Exception as exc:
            return _err(f"GitHub API error: {exc}")
    return _ok({"repos": repos, "count": len(repos)})


async def portal_propose_remediation(arguments: dict[str, Any]) -> dict[str, Any]:
    """HITL write: stage a plan on the incident; never executes it."""
    try:
        incident_id = int(arguments["incident_id"])
    except (KeyError, TypeError, ValueError):
        return _err("incident_id is required")
    plan = arguments.get("plan")
    if isinstance(plan, str):
        steps = [s.strip() for s in plan.splitlines() if s.strip()]
    elif isinstance(plan, list):
        steps = [str(s).strip() for s in plan if str(s).strip()]
    else:
        return _err("plan must be a string or list of strings")
    if not steps:
        return _err("plan cannot be empty")

    tenant_id = _tenant(arguments)
    existing = get_incident(incident_id, tenant_id=tenant_id)
    if existing is None:
        return _err(f"Incident {incident_id} not found")

    updated = update_incident_status(
        incident_id,
        status="AWAITING_APPROVAL",
        proposed_remediation_plan=json.dumps(steps),
    )
    return _ok(
        {
            "status": "pending_approval",
            "hitl": True,
            "incident_id": incident_id,
            "message": "Remediation proposed — approve in the portal before execution.",
            "incident": updated,
        }
    )


async def portal_run_agent(arguments: dict[str, Any]) -> dict[str, Any]:
    """HITL write: queue an agent run as pending_approval; do not execute commands."""
    agent = (arguments.get("agent") or "").strip()
    task = (arguments.get("task") or "").strip()
    if not agent or not task:
        return _err("agent and task are required")

    params = arguments.get("params") if isinstance(arguments.get("params"), dict) else {}
    user_id = str(arguments.get("user_id") or "mcp")
    workspace_id = str(arguments.get("workspace_id") or "")
    tenant_id = _tenant(arguments)
    environment = str(arguments.get("environment") or "development")

    # Validate agent exists without running it.
    try:
        from ..agents import get_agent

        get_agent(agent)
    except Exception as exc:
        return _err(f"Unknown agent '{agent}': {exc}")

    with Session(engine) as session:
        row = AgentRun(
            agent=agent,
            status="pending_approval",
            summary=f"MCP queued {agent}: {task[:200]}",
            details_json=json.dumps({"source": "portal_mcp", "params": params}, default=str),
            requires_approval=True,
            approval_payload_json=json.dumps(
                {
                    "agent": agent,
                    "task": task,
                    "params": params,
                    "source": "portal_mcp",
                    "commands": [],
                },
                default=str,
            ),
            triggered_by=user_id,
            user_id=user_id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
            environment=environment,
            task=task,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        run_id = row.id

    return _ok(
        {
            "status": "pending_approval",
            "hitl": True,
            "run_id": run_id,
            "agent": agent,
            "message": "Agent run queued for human approval in the portal.",
        }
    )


TOOL_HANDLERS = {
    "portal_list_incidents": portal_list_incidents,
    "portal_get_incident": portal_get_incident,
    "portal_list_catalog_services": portal_list_catalog_services,
    "portal_search": portal_search,
    "portal_health_summary": portal_health_summary,
    "portal_list_github_repos": portal_list_github_repos,
    "portal_propose_remediation": portal_propose_remediation,
    "portal_run_agent": portal_run_agent,
}


async def dispatch_tool(name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return _err(f"Unknown tool: {name}")
    return await handler(arguments or {})
