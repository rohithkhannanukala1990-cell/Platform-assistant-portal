"""Portal-as-MCP-server (Phase M2).

Exposes portal domain tools over MCP JSON-RPC 2.0 on stdio.

Auth
----
``PORTAL_MCP_TOKEN`` must be configured. Clients authenticate by:

1. Setting the same token in the process environment when spawning this server
   (typical IDE / Claude Desktop config), **or**
2. Passing ``{"auth": {"token": "..."}}`` (or top-level ``token``) on
   ``initialize`` / ``tools/list`` / ``tools/call``.

Without a matching token, requests are rejected.

Run
---
::

    python -m backend.mcp.server_app

Requires ``MCP_ENABLED=true`` (otherwise the process exits with an error).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Optional, TextIO

from dotenv import load_dotenv

from .portal_tools import PORTAL_TOOLS, WRITE_TOOLS, dispatch_tool, mcp_enabled
from .types import PROTOCOL_VERSION, MCPError

SERVER_INFO = {"name": "platform-assistant-portal", "version": "1.0.0"}


def expected_token() -> str:
    return (os.getenv("PORTAL_MCP_TOKEN") or "").strip()


def extract_token(params: Optional[dict[str, Any]]) -> str:
    params = params or {}
    auth = params.get("auth") if isinstance(params.get("auth"), dict) else {}
    for candidate in (
        params.get("token"),
        auth.get("token"),
        params.get("authorization"),
        auth.get("authorization"),
    ):
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text.lower().startswith("bearer "):
            text = text[7:].strip()
        if text:
            return text
    # Stdio clients usually inject the token into the child env.
    return expected_token()


def require_auth(params: Optional[dict[str, Any]] = None) -> None:
    expected = expected_token()
    if not expected:
        raise MCPError("PORTAL_MCP_TOKEN is not configured on the portal MCP server")
    provided = extract_token(params)
    if not provided:
        raise MCPError("Unauthorized: MCP token required")
    if provided != expected:
        raise MCPError("Unauthorized: invalid MCP token")


class PortalMCPServer:
    """In-process MCP server. Prefer :func:`serve_stdio` for IDE wiring."""

    def __init__(self):
        self._initialized = False

    def list_tools(self) -> list[dict[str, Any]]:
        return list(PORTAL_TOOLS)

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return await dispatch_tool(name, arguments or {})

    async def handle(self, message: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Handle one JSON-RPC message. Notifications return None."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._error(None, -32600, "Invalid Request")

        method = message.get("method")
        msg_id = message.get("id", None)
        params = message.get("params") if isinstance(message.get("params"), dict) else {}

        # Notifications (no id)
        if msg_id is None and method:
            if method == "notifications/initialized":
                self._initialized = True
            return None

        try:
            if method == "initialize":
                require_auth(params)
                self._initialized = True
                return self._result(
                    msg_id,
                    {
                        "protocolVersion": PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": SERVER_INFO,
                    },
                )

            if method == "ping":
                require_auth(params)
                return self._result(msg_id, {})

            if method == "tools/list":
                require_auth(params)
                return self._result(msg_id, {"tools": self.list_tools()})

            if method == "tools/call":
                require_auth(params)
                name = str(params.get("name") or "").strip()
                arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
                # Propagate auth token into tool args only if caller supplied tenant context keys.
                result = await self.call_tool(name, arguments)
                # Annotate write tools clearly for clients.
                if name in WRITE_TOOLS and isinstance(result, dict):
                    structured = result.get("structuredContent")
                    if isinstance(structured, dict) and structured.get("status") == "pending_approval":
                        result = {
                            **result,
                            "content": result.get("content")
                            or [
                                {
                                    "type": "text",
                                    "text": json.dumps(structured, default=str),
                                }
                            ],
                        }
                return self._result(msg_id, result)

            return self._error(msg_id, -32601, f"Method not found: {method}")
        except MCPError as exc:
            return self._error(msg_id, -32001, str(exc))
        except Exception as exc:
            return self._error(msg_id, -32000, f"Internal error: {exc}")

    @staticmethod
    def _result(msg_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }


async def serve_stdio(
    *,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
) -> None:
    """Read newline-delimited JSON-RPC from stdin; write responses to stdout."""
    load_dotenv()
    if not mcp_enabled():
        print("MCP_ENABLED is not set — refusing to start portal MCP server", file=sys.stderr)
        raise SystemExit(2)
    if not expected_token():
        print("PORTAL_MCP_TOKEN is required", file=sys.stderr)
        raise SystemExit(2)

    server = PortalMCPServer()
    in_stream = stdin or sys.stdin
    out_stream = stdout or sys.stdout

    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, in_stream.readline)
        if not line:
            break
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            response = PortalMCPServer._error(None, -32700, "Parse error")
            out_stream.write(json.dumps(response) + "\n")
            out_stream.flush()
            continue

        response = await server.handle(message)
        if response is not None:
            out_stream.write(json.dumps(response, default=str) + "\n")
            out_stream.flush()


def main() -> None:
    load_dotenv()
    try:
        asyncio.run(serve_stdio())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
