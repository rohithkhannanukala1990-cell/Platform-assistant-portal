"""MCP client package (Phase M1).

The portal is an MCP *client* only: it connects out to external MCP servers.
MCP is an edge protocol here — it never bypasses auth, tenant scoping, or HITL.
Every tool call must go through :mod:`backend.mcp.hitl_bridge`.
"""

from .client import MCPClient
from .types import (
    MCPError,
    MCPServerConfig,
    MCPTool,
    MCPToolResult,
    is_dangerous,
    is_read_only,
)

__all__ = [
    "MCPClient",
    "MCPError",
    "MCPServerConfig",
    "MCPTool",
    "MCPToolResult",
    "is_dangerous",
    "is_read_only",
]
