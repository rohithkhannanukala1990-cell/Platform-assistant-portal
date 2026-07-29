"""The only sanctioned path to run an MCP tool.

Every ``tools/call`` is recorded in ``mcp_tool_calls`` and audited. Read-only
tools on servers that do not force HITL run immediately; write or otherwise
dangerous tools stop at ``pending_approval`` until a human approves them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlmodel import Session, select

from ..auth import User, normalize_role, write_audit
from ..database import engine
from ..db.models.mcp_models import MCPServer, MCPToolCall
from ..observability.logger import logger
from ..services.approval_claim import claim_mcp_call
from . import registry
from .types import MCPTool, is_dangerous

STATUS_PENDING = "pending_approval"
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"
STATUS_ERROR = "error"
STATUS_EXECUTING = "executing"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def call_to_dict(row: MCPToolCall) -> dict[str, Any]:
    def _loads(raw: str, fallback: Any) -> Any:
        try:
            return json.loads(raw or "")
        except (TypeError, json.JSONDecodeError):
            return fallback

    return {
        "id": row.id,
        "server_id": row.server_id,
        "server_name": row.server_name,
        "tool_name": row.tool_name,
        "arguments": _loads(row.arguments_json, {}),
        "result": _loads(row.result_json, {}),
        "status": row.status,
        "requires_hitl": bool(row.requires_hitl),
        "dangerous": bool(row.dangerous),
        "source": row.source,
        "requested_by": row.requested_by,
        "approved_by": row.approved_by,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
        "tenant_id": row.tenant_id,
        "created_at": row.created_at.isoformat(),
    }


def requires_approval(server: MCPServer, tool: MCPTool) -> bool:
    """Servers can force approval for everything; otherwise writes need it."""
    return bool(server.require_hitl) or is_dangerous(tool)


def _audit(user: Optional[User], event_type: str, server: str, tool: str, detail: str, ip_address: str = "") -> None:
    try:
        write_audit(
            actor=getattr(user, "username", "") or "system",
            actor_role=normalize_role(getattr(user, "role", "") or "User"),
            event_type=event_type,
            resource=f"mcp:{server}/{tool}",
            detail=detail,
            ip_address=ip_address,
        )
    except Exception:
        logger.warning("MCP audit write failed", extra={"source": "mcp", "tool": tool})


def _persist(row: MCPToolCall) -> MCPToolCall:
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


async def _execute(server: MCPServer, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    client = registry.client_for_server(server)
    try:
        result = await client.call_tool(tool_name, arguments)
    finally:
        await client.close()
    return result.to_dict()


def _resolve_server(server_id: str, tenant_id: str) -> MCPServer:
    server = registry.get_server(server_id, tenant_id)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if not server.enabled:
        raise HTTPException(status_code=400, detail=f"MCP server '{server.name}' is disabled")
    return server


async def call_tool(
    *,
    server_id: str,
    tool_name: str,
    arguments: Optional[dict[str, Any]] = None,
    user: Optional[User] = None,
    tenant_id: str = "default",
    source: str = "api",
    ip_address: str = "",
) -> dict[str, Any]:
    """Auth/tenant-scoped tool call. Returns a persisted call record as a dict."""
    server = _resolve_server(server_id, tenant_id)
    tool_name = (tool_name or "").strip()

    if not registry.tool_allowed(server, tool_name):
        _audit(user, "mcp_tool_blocked", server.name, tool_name, "outcome=denied reason=not_allowlisted", ip_address)
        raise HTTPException(status_code=403, detail=f"Tool '{tool_name}' is not allowlisted for this server")

    tool = await registry.find_tool(server, tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found on '{server.name}'")

    needs_approval = requires_approval(server, tool)
    row = MCPToolCall(
        server_id=server.id,
        server_name=server.name,
        tool_name=tool_name,
        arguments_json=json.dumps(arguments or {}, default=str),
        status=STATUS_PENDING,
        requires_hitl=needs_approval,
        dangerous=is_dangerous(tool),
        source=source,
        requested_by=getattr(user, "username", "") or "system",
        tenant_id=tenant_id or "default",
    )

    if needs_approval:
        row = _persist(row)
        _audit(
            user,
            "mcp_tool_pending",
            server.name,
            tool_name,
            f"outcome=pending_approval call_id={row.id} dangerous={row.dangerous}",
            ip_address,
        )
        return call_to_dict(row)

    try:
        result = await _execute(server, tool_name, arguments or {})
        row.status = STATUS_COMPLETED if result.get("ok") else STATUS_ERROR
        row.result_json = json.dumps(result, default=str)
    except Exception as exc:
        row.status = STATUS_ERROR
        row.result_json = json.dumps({"ok": False, "error": str(exc)}, default=str)
        logger.error("MCP tool call failed", extra={"source": "mcp", "tool": tool_name, "error": str(exc)})
    row.executed_at = _now()
    row = _persist(row)
    _audit(user, "mcp_tool_call", server.name, tool_name, f"outcome={row.status} call_id={row.id}", ip_address)
    return call_to_dict(row)


def get_call(call_id: str, tenant_id: Optional[str] = None) -> Optional[MCPToolCall]:
    with Session(engine) as session:
        row = session.get(MCPToolCall, (call_id or "").strip())
    if row is None:
        return None
    if tenant_id and (row.tenant_id or "default") != tenant_id:
        return None
    return row


def list_calls(tenant_id: Optional[str] = None, *, status: Optional[str] = None, limit: int = 50) -> list[MCPToolCall]:
    with Session(engine) as session:
        query = select(MCPToolCall)
        if tenant_id:
            query = query.where(MCPToolCall.tenant_id == tenant_id)
        if status:
            query = query.where(MCPToolCall.status == status)
        query = query.order_by(MCPToolCall.created_at.desc()).limit(max(1, min(limit, 100)))
        return list(session.exec(query).all())


async def approve_call(
    *,
    call_id: str,
    user: Optional[User] = None,
    tenant_id: str = "default",
    ip_address: str = "",
) -> dict[str, Any]:
    """Run a pending call after human approval."""
    row = get_call(call_id, tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP call not found")
    if row.status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail="MCP call is not pending approval")

    server = _resolve_server(row.server_id, tenant_id)
    approver = getattr(user, "username", "") or "admin"
    try:
        arguments = json.loads(row.arguments_json or "{}")
    except json.JSONDecodeError:
        arguments = {}

    with Session(engine) as session:
        if not claim_mcp_call(
            session, row.id, to_status=STATUS_EXECUTING, approved_by=approver
        ):
            raise HTTPException(
                status_code=409, detail="MCP call already claimed or not pending approval"
            )

    try:
        result = await _execute(server, row.tool_name, arguments)
        status = STATUS_COMPLETED if result.get("ok") else STATUS_ERROR
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
        status = STATUS_ERROR

    with Session(engine) as session:
        current = session.get(MCPToolCall, row.id)
        if current is None:
            raise HTTPException(status_code=404, detail="MCP call not found")
        current.status = status
        current.result_json = json.dumps(result, default=str)
        current.approved_by = approver
        current.approved_at = _now()
        current.executed_at = _now()
        session.add(current)
        session.commit()
        session.refresh(current)
        payload = call_to_dict(current)

    _audit(user, "mcp_tool_approved", row.server_name, row.tool_name, f"outcome={status} call_id={row.id}", ip_address)
    return payload


def reject_call(
    *,
    call_id: str,
    user: Optional[User] = None,
    tenant_id: str = "default",
    reason: str = "",
    ip_address: str = "",
) -> dict[str, Any]:
    row = get_call(call_id, tenant_id)
    if row is None:
        raise HTTPException(status_code=404, detail="MCP call not found")
    if row.status != STATUS_PENDING:
        raise HTTPException(status_code=400, detail="MCP call is not pending approval")

    rejector = getattr(user, "username", "") or "admin"
    with Session(engine) as session:
        if not claim_mcp_call(
            session, row.id, to_status=STATUS_REJECTED, approved_by=rejector
        ):
            raise HTTPException(
                status_code=409, detail="MCP call already claimed or not pending approval"
            )
        current = session.get(MCPToolCall, row.id)
        current.result_json = json.dumps(
            {"ok": False, "rejected_by": rejector, "reason": reason or ""}
        )
        session.add(current)
        session.commit()
        session.refresh(current)
        payload = call_to_dict(current)

    _audit(user, "mcp_tool_rejected", row.server_name, row.tool_name, f"outcome=rejected call_id={row.id}", ip_address)
    return payload
