"""MCP wire types and read/write tool classification (Phase M1).

Protocol implementation choice
------------------------------
This package speaks MCP's JSON-RPC 2.0 directly instead of depending on the
official ``mcp`` Python SDK. Reasons:

* the SDK is not currently a dependency of this backend, and M1 only needs
  three methods (``initialize``, ``tools/list``, ``tools/call``);
* the SDK owns its own anyio task-group session lifecycle, which does not map
  cleanly onto short-lived request-scoped calls from FastAPI handlers;
* a thin client keeps tests hermetic (transports are trivially mockable).

``MCPClient`` is the only module that touches the wire, so swapping in the
official SDK later is a single-file change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

PROTOCOL_VERSION = "2024-11-05"

TRANSPORT_STDIO = "stdio"
TRANSPORT_SSE = "sse"
VALID_TRANSPORTS = (TRANSPORT_STDIO, TRANSPORT_SSE)

# Verbs that only observe state — safe to auto-run without human approval.
READ_ONLY_PREFIXES = (
    "list", "get", "read", "search", "fetch", "describe", "query", "show",
    "find", "inspect", "count", "diff", "status", "view", "lookup", "resolve",
)

# Verbs that mutate state or leave the platform — always human-approved.
DANGEROUS_KEYWORDS = (
    "delete", "remove", "drop", "destroy", "terminate", "kill", "write",
    "create", "update", "patch", "put", "post", "apply", "deploy", "merge",
    "push", "rotate", "revoke", "grant", "exec", "execute", "run", "restart",
    "scale", "shutdown", "truncate", "purge", "publish", "send", "modify",
    "set", "install", "uninstall", "move", "rename", "upload", "close",
    "cancel", "approve", "invite", "transfer", "pay",
)


class MCPError(Exception):
    """Transport, protocol, or server-reported MCP failure."""


@dataclass
class MCPServerConfig:
    """Connection details for one external MCP server (secrets decrypted)."""

    id: str
    name: str
    transport: str = TRANSPORT_STDIO
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if self.transport not in VALID_TRANSPORTS:
            raise MCPError(f"Unsupported transport '{self.transport}'")
        if self.transport == TRANSPORT_STDIO and not (self.command or "").strip():
            raise MCPError("stdio transport requires a command")
        if self.transport == TRANSPORT_SSE and not (self.url or "").strip():
            raise MCPError("sse transport requires a url")


@dataclass
class MCPTool:
    """A tool advertised by an MCP server's ``tools/list``."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)
    server_id: str = ""
    server_name: str = ""

    @classmethod
    def from_wire(cls, raw: dict[str, Any], *, server_id: str = "", server_name: str = "") -> "MCPTool":
        return cls(
            name=str(raw.get("name") or ""),
            description=str(raw.get("description") or ""),
            input_schema=raw.get("inputSchema") or raw.get("input_schema") or {},
            annotations=raw.get("annotations") or {},
            server_id=server_id,
            server_name=server_name,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "server_name": self.server_name,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "annotations": self.annotations,
            "read_only": is_read_only(self),
            "dangerous": is_dangerous(self),
        }


@dataclass
class MCPToolResult:
    """Normalized ``tools/call`` outcome."""

    ok: bool
    text: str = ""
    content: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "text": self.text, "content": self.content, "error": self.error}


def _hint(tool: MCPTool, key: str) -> Optional[bool]:
    value = (tool.annotations or {}).get(key)
    return bool(value) if isinstance(value, bool) else None


def is_read_only(tool: MCPTool) -> bool:
    """True when a tool only observes state, so it may auto-run.

    Server-provided annotations win; otherwise fall back to verb heuristics and
    fail closed (unknown verbs are treated as writes).
    """
    read_hint = _hint(tool, "readOnlyHint")
    if read_hint is not None:
        return read_hint
    if _hint(tool, "destructiveHint"):
        return False

    name = (tool.name or "").strip().lower()
    if not name:
        return False
    head = name.replace("-", "_").replace(".", "_").replace("/", "_").split("_")[0]
    if head in DANGEROUS_KEYWORDS:
        return False
    return head in READ_ONLY_PREFIXES


def is_dangerous(tool: MCPTool) -> bool:
    """True when a tool mutates state and must go through human approval."""
    return not is_read_only(tool)
