"""MCP server registry: persistence, secret handling, and tool discovery."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, select

from ..database import engine
from ..db.models.mcp_models import MCPServer
from ..services.secrets import decrypt_secret, encrypt_secret
from .client import MCPClient
from .types import MCPError, MCPServerConfig, MCPTool, VALID_TRANSPORTS


def _json_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _json_obj(raw: str | None) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}


def decrypt_env(row: MCPServer) -> dict[str, str]:
    if not (row.env_encrypted or "").strip():
        return {}
    return _json_obj(decrypt_secret(row.env_encrypted or ""))


def encrypt_env(env: dict[str, Any] | None) -> Optional[str]:
    clean = {str(k): str(v) for k, v in (env or {}).items() if str(k).strip()}
    if not clean:
        return None
    return encrypt_secret(json.dumps(clean))


def server_to_config(row: MCPServer) -> MCPServerConfig:
    """Build a connection config with secrets decrypted (server-side only)."""
    return MCPServerConfig(
        id=row.id,
        name=row.name,
        transport=row.transport,
        command=row.command or "",
        args=_json_list(row.args_json),
        url=row.url or "",
        env=decrypt_env(row),
    )


def server_to_dict(row: MCPServer) -> dict[str, Any]:
    """Masked API representation — env values never leave the backend."""
    env = decrypt_env(row)
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "transport": row.transport,
        "command": row.command,
        "args": _json_list(row.args_json),
        "url": row.url,
        # Names only, so operators can confirm what is set without exposing values.
        "env_keys": sorted(env.keys()),
        "has_env": bool(env),
        "enabled": bool(row.enabled),
        "require_hitl": bool(row.require_hitl),
        "allowlist": _json_list(row.allowlist_json),
        "tenant_id": row.tenant_id,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def validate_transport(transport: str) -> str:
    value = (transport or "").strip().lower()
    if value not in VALID_TRANSPORTS:
        raise MCPError(f"transport must be one of {', '.join(VALID_TRANSPORTS)}")
    return value


# ── persistence ───────────────────────────────────────────────────────────────


def list_servers(tenant_id: Optional[str] = None, *, enabled_only: bool = False) -> list[MCPServer]:
    with Session(engine) as session:
        query = select(MCPServer)
        if tenant_id:
            query = query.where(MCPServer.tenant_id == tenant_id)
        if enabled_only:
            query = query.where(MCPServer.enabled == True)  # noqa: E712
        return list(session.exec(query.order_by(MCPServer.created_at)).all())


def get_server(server_id: str, tenant_id: Optional[str] = None) -> Optional[MCPServer]:
    with Session(engine) as session:
        row = session.get(MCPServer, (server_id or "").strip())
    if row is None:
        return None
    if tenant_id and (row.tenant_id or "default") != tenant_id:
        return None
    return row


def get_server_by_name(name: str, tenant_id: Optional[str] = None) -> Optional[MCPServer]:
    target = (name or "").strip().lower()
    for row in list_servers(tenant_id):
        if (row.name or "").strip().lower() == target:
            return row
    return None


def create_server(
    *,
    name: str,
    transport: str,
    description: str = "",
    command: str = "",
    args: Optional[list[str]] = None,
    url: str = "",
    env: Optional[dict[str, Any]] = None,
    enabled: bool = True,
    require_hitl: bool = True,
    allowlist: Optional[list[str]] = None,
    tenant_id: str = "default",
    created_by: str = "",
) -> MCPServer:
    row = MCPServer(
        name=(name or "").strip(),
        description=(description or "").strip(),
        transport=validate_transport(transport),
        command=(command or "").strip(),
        args_json=json.dumps([str(a) for a in (args or [])]),
        url=(url or "").strip(),
        env_encrypted=encrypt_env(env),
        enabled=bool(enabled),
        require_hitl=bool(require_hitl),
        allowlist_json=json.dumps([str(a) for a in (allowlist or [])]),
        tenant_id=tenant_id or "default",
        created_by=created_by or "",
    )
    server_to_config(row).validate()
    with Session(engine) as session:
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def update_server(row: MCPServer, changes: dict[str, Any]) -> MCPServer:
    with Session(engine) as session:
        current = session.get(MCPServer, row.id)
        if current is None:
            raise MCPError("MCP server not found")

        for field_name in ("name", "description", "command", "url"):
            if changes.get(field_name) is not None:
                setattr(current, field_name, str(changes[field_name]).strip())
        if changes.get("transport") is not None:
            current.transport = validate_transport(str(changes["transport"]))
        if changes.get("args") is not None:
            current.args_json = json.dumps([str(a) for a in (changes["args"] or [])])
        if changes.get("allowlist") is not None:
            current.allowlist_json = json.dumps([str(a) for a in (changes["allowlist"] or [])])
        if changes.get("enabled") is not None:
            current.enabled = bool(changes["enabled"])
        if changes.get("require_hitl") is not None:
            current.require_hitl = bool(changes["require_hitl"])
        # Omitted / empty env leaves the stored secret untouched.
        if changes.get("env"):
            merged = {**decrypt_env(current), **{str(k): str(v) for k, v in changes["env"].items()}}
            current.env_encrypted = encrypt_env(merged)
        if changes.get("clear_env"):
            current.env_encrypted = None

        current.updated_at = datetime.now(timezone.utc)
        server_to_config(current).validate()
        session.add(current)
        session.commit()
        session.refresh(current)
        return current


def delete_server(server_id: str) -> bool:
    with Session(engine) as session:
        row = session.get(MCPServer, server_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


# ── discovery ─────────────────────────────────────────────────────────────────


def client_for_server(row: MCPServer) -> MCPClient:
    """Factory kept module-level so tests can patch it with a fake client."""
    return MCPClient(server_to_config(row))


def tool_allowed(row: MCPServer, tool_name: str) -> bool:
    allowlist = _json_list(row.allowlist_json)
    if not allowlist:
        return True
    return (tool_name or "").strip() in allowlist


async def list_tools_for_server(row: MCPServer) -> list[MCPTool]:
    """Discover tools, filtered by the server allowlist."""
    client = client_for_server(row)
    try:
        tools = await client.list_tools()
    finally:
        await client.close()
    return [t for t in tools if tool_allowed(row, t.name)]


async def find_tool(row: MCPServer, tool_name: str) -> Optional[MCPTool]:
    for tool in await list_tools_for_server(row):
        if tool.name == tool_name:
            return tool
    return None


async def list_all_tools(tenant_id: Optional[str] = None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Tools across every enabled server, plus per-server errors (never raises)."""
    tools: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for row in list_servers(tenant_id, enabled_only=True):
        try:
            for tool in await list_tools_for_server(row):
                payload = tool.to_dict()
                payload["require_approval"] = bool(row.require_hitl) or payload["dangerous"]
                tools.append(payload)
        except Exception as exc:
            errors.append({"server_id": row.id, "server_name": row.name, "error": str(exc)})
    return tools, errors


async def test_server(row: MCPServer) -> dict[str, Any]:
    """Connect + tools/list, reporting latency instead of raising."""
    started = time.perf_counter()
    try:
        tools = await list_tools_for_server(row)
    except Exception as exc:
        return {
            "connected": False,
            "error": str(exc),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "tools": [],
        }
    return {
        "connected": True,
        "error": None,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "tool_count": len(tools),
        "tools": [t.to_dict() for t in tools],
    }
