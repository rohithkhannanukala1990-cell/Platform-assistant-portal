"""MCP client API (/api/mcp): server registry, tool catalog, and gated calls."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from ..auth import User, get_current_user, require_admin, write_audit
from ..mcp import hitl_bridge, registry
from ..mcp.types import MCPError
from ..services.isolation import require_tenant

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class ServerCreate(BaseModel):
    name: str
    transport: str = "stdio"
    description: str = ""
    command: str = ""
    args: list[str] = []
    url: str = ""
    # Secret values (API keys, tokens). Encrypted at rest, never returned.
    env: dict[str, str] = {}
    enabled: bool = True
    require_hitl: bool = True
    allowlist: list[str] = []


class ServerUpdate(BaseModel):
    name: Optional[str] = None
    transport: Optional[str] = None
    description: Optional[str] = None
    command: Optional[str] = None
    args: Optional[list[str]] = None
    url: Optional[str] = None
    env: Optional[dict[str, str]] = None  # omit / empty keeps existing secrets
    clear_env: Optional[bool] = None
    enabled: Optional[bool] = None
    require_hitl: Optional[bool] = None
    allowlist: Optional[list[str]] = None


class ToolCallRequest(BaseModel):
    server_id: str
    tool: str
    arguments: dict[str, Any] = {}


class RejectRequest(BaseModel):
    reason: str = ""


def _client_ip(request: Request) -> str:
    return request.client.host if request and request.client else ""


def _require_server(server_id: str, tenant_id: str):
    server = registry.get_server(server_id, tenant_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


# ── server registry (admin) ───────────────────────────────────────────────────


@router.get("/servers")
def list_servers(request: Request, _admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    return [registry.server_to_dict(row) for row in registry.list_servers(tenant_id)]


@router.post("/servers", status_code=status.HTTP_201_CREATED)
def create_server(body: ServerCreate, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    if not (body.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if registry.get_server_by_name(body.name, tenant_id) is not None:
        raise HTTPException(status_code=400, detail=f"MCP server '{body.name}' already exists")

    try:
        row = registry.create_server(
            name=body.name,
            transport=body.transport,
            description=body.description,
            command=body.command,
            args=body.args,
            url=body.url,
            env=body.env,
            enabled=body.enabled,
            require_hitl=body.require_hitl,
            allowlist=body.allowlist,
            tenant_id=tenant_id,
            created_by=admin.username,
        )
    except MCPError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="mcp_server_created",
        resource=f"mcp:{row.name}",
        detail=f"transport={row.transport} require_hitl={row.require_hitl}",
        ip_address=_client_ip(request),
    )
    return registry.server_to_dict(row)


@router.put("/servers/{server_id}")
def update_server(server_id: str, body: ServerUpdate, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    row = _require_server(server_id, tenant_id)
    try:
        updated = registry.update_server(row, body.model_dump(exclude_unset=True))
    except MCPError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="mcp_server_updated",
        resource=f"mcp:{updated.name}",
        detail=f"enabled={updated.enabled} require_hitl={updated.require_hitl}",
        ip_address=_client_ip(request),
    )
    return registry.server_to_dict(updated)


@router.delete("/servers/{server_id}")
def delete_server(server_id: str, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    row = _require_server(server_id, tenant_id)
    registry.delete_server(row.id)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="mcp_server_deleted",
        resource=f"mcp:{row.name}",
        detail="",
        ip_address=_client_ip(request),
    )
    return {"ok": True, "id": row.id}


@router.post("/servers/{server_id}/test")
async def test_server(server_id: str, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    row = _require_server(server_id, tenant_id)
    result = await registry.test_server(row)
    write_audit(
        actor=admin.username,
        actor_role=admin.role,
        event_type="mcp_server_tested",
        resource=f"mcp:{row.name}",
        detail=f"connected={result.get('connected')}",
        ip_address=_client_ip(request),
    )
    return result


# ── tools ─────────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools(request: Request, _user: User = Depends(get_current_user)):
    """Read-only catalog of tools across enabled servers (allowlist applied)."""
    tenant_id = require_tenant(request)
    tools, errors = await registry.list_all_tools(tenant_id)
    return {"tools": tools, "errors": errors, "count": len(tools)}


@router.post("/tools/call")
async def call_tool(body: ToolCallRequest, request: Request, user: User = Depends(get_current_user)):
    """Never calls MCP directly — always through the HITL bridge."""
    tenant_id = require_tenant(request)
    return await hitl_bridge.call_tool(
        server_id=body.server_id,
        tool_name=body.tool,
        arguments=body.arguments,
        user=user,
        tenant_id=tenant_id,
        source="api",
        ip_address=_client_ip(request),
    )


# ── HITL queue ────────────────────────────────────────────────────────────────


@router.get("/calls")
def list_calls(
    request: Request,
    call_status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    _user: User = Depends(get_current_user),
):
    tenant_id = require_tenant(request)
    rows = hitl_bridge.list_calls(tenant_id, status=call_status, limit=limit)
    return [hitl_bridge.call_to_dict(r) for r in rows]


@router.get("/calls/pending")
def list_pending_calls(request: Request, _user: User = Depends(get_current_user)):
    tenant_id = require_tenant(request)
    rows = hitl_bridge.list_calls(tenant_id, status=hitl_bridge.STATUS_PENDING)
    return [hitl_bridge.call_to_dict(r) for r in rows]


@router.post("/calls/{call_id}/approve")
async def approve_call(call_id: str, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    return await hitl_bridge.approve_call(
        call_id=call_id,
        user=admin,
        tenant_id=tenant_id,
        ip_address=_client_ip(request),
    )


@router.post("/calls/{call_id}/reject")
def reject_call(call_id: str, body: RejectRequest, request: Request, admin: User = Depends(require_admin)):
    tenant_id = require_tenant(request)
    return hitl_bridge.reject_call(
        call_id=call_id,
        user=admin,
        tenant_id=tenant_id,
        reason=body.reason,
        ip_address=_client_ip(request),
    )
