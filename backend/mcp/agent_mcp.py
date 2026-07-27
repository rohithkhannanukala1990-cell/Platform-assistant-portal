"""Helpers so agents can consume MCP tool catalogs / GitHub via MCP when enabled."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlmodel import Session

from ..context import PlatformContext
from .portal_tools import mcp_enabled, portal_list_github_repos
from . import registry

# External MCP tool names we treat as GitHub repo listers.
_GITHUB_LIST_TOOL_NAMES = {
    "list_repos",
    "list_repositories",
    "github_list_repos",
    "portal_list_github_repos",
}


async def mcp_tool_catalog(tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
    """External MCP tools + portal server tools, when MCP is enabled."""
    if not mcp_enabled():
        return []
    tools: list[dict[str, Any]] = []
    try:
        external, _errors = await registry.list_all_tools(tenant_id)
        tools.extend(external)
    except Exception:
        pass
    # Always advertise portal server tools in-agent when MCP is on.
    from .portal_tools import PORTAL_TOOLS

    for t in PORTAL_TOOLS:
        tools.append(
            {
                "server_id": "portal",
                "server_name": "portal",
                "name": t["name"],
                "description": t.get("description") or "",
                "input_schema": t.get("inputSchema") or {},
                "annotations": t.get("annotations") or {},
                "read_only": bool((t.get("annotations") or {}).get("readOnlyHint")),
                "dangerous": not bool((t.get("annotations") or {}).get("readOnlyHint")),
                "require_approval": not bool((t.get("annotations") or {}).get("readOnlyHint")),
            }
        )
    return tools


def format_mcp_catalog_for_prompt(tools: list[dict[str, Any]], *, limit: int = 40) -> str:
    if not tools:
        return ""
    lines = ["MCP tools available (prefer these when relevant):"]
    for tool in tools[:limit]:
        flag = " [approval]" if tool.get("require_approval") or tool.get("dangerous") else " [read]"
        lines.append(
            f"- {tool.get('server_name')}/{tool.get('name')}{flag}: "
            f"{(tool.get('description') or '')[:120]}"
        )
    return "\n".join(lines)


def _external_github_list_tool(tools: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for tool in tools:
        name = str(tool.get("name") or "").strip().lower()
        if name in _GITHUB_LIST_TOOL_NAMES or (
            "github" in name and "repo" in name and name.startswith(("list", "get"))
        ):
            if tool.get("server_id") and tool.get("server_id") != "portal":
                return tool
    return None


async def list_github_repos_prefer_mcp(
    context: PlatformContext,
    db: Session,
    *,
    per_page: int = 20,
) -> tuple[Optional[list[dict[str, Any]]], str]:
    """Prefer external MCP GitHub tools when configured; else portal scoped connector.

    Returns ``(repos_or_none, source)`` where source is
    ``mcp`` | ``connector`` | ``unavailable``.
    """
    _ = db  # reserved for future scoped lookups
    tenant_id = context.tenant_id or "default"

    if mcp_enabled():
        try:
            external, _ = await registry.list_all_tools(tenant_id)
        except Exception:
            external = []
        tool = _external_github_list_tool(external)
        if tool is not None:
            from . import hitl_bridge

            call = await hitl_bridge.call_tool(
                server_id=str(tool["server_id"]),
                tool_name=str(tool["name"]),
                arguments={"per_page": per_page},
                tenant_id=tenant_id,
                source="agent",
            )
            if call.get("status") == "completed":
                result = call.get("result") or {}
                text = result.get("text") or ""
                try:
                    payload = json.loads(text) if text.startswith("{") or text.startswith("[") else result
                except json.JSONDecodeError:
                    payload = result
                repos = None
                if isinstance(payload, list):
                    repos = payload
                elif isinstance(payload, dict):
                    repos = payload.get("repos") or payload.get("repositories")
                if isinstance(repos, list):
                    return repos, "mcp"

        # Fall back to the portal's own GitHub tool (scoped connector under the hood).
        outcome = await portal_list_github_repos(
            {
                "per_page": per_page,
                "user_id": context.user_id or "",
                "workspace_id": context.workspace_id or "",
                "tenant_id": tenant_id,
            }
        )
        if not outcome.get("isError"):
            structured = outcome.get("structuredContent") or {}
            repos = structured.get("repos") if isinstance(structured, dict) else None
            if isinstance(repos, list):
                return repos, "mcp"

    from ..services.github_access import try_github_connector_from_context

    connector = try_github_connector_from_context(context, db=db)
    if connector is None:
        return None, "unavailable"
    try:
        repos = await connector.list_repos(per_page=per_page)
        return repos, "connector"
    except Exception:
        return None, "unavailable"
