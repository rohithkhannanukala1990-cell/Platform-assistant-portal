"""Minimal MCP client: JSON-RPC 2.0 over stdio or HTTP/SSE.

See ``types.py`` for why this speaks the protocol directly instead of using the
official ``mcp`` SDK. Only ``initialize``, ``tools/list``, and ``tools/call``
are implemented — everything else an MCP server offers is out of scope for M1.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

from .types import (
    PROTOCOL_VERSION,
    TRANSPORT_SSE,
    TRANSPORT_STDIO,
    MCPError,
    MCPServerConfig,
    MCPTool,
    MCPToolResult,
)

CLIENT_INFO = {"name": "platform-assistant-portal", "version": "1.0.0"}
DEFAULT_TIMEOUT_SECONDS = 20.0


def _normalize_call_result(payload: dict[str, Any]) -> MCPToolResult:
    content = payload.get("content")
    items = [c for c in content if isinstance(c, dict)] if isinstance(content, list) else []
    texts = [str(c.get("text") or "") for c in items if c.get("type") == "text"]
    text = "\n".join(t for t in texts if t)
    if not text and not items:
        text = json.dumps(payload, default=str)
    is_error = bool(payload.get("isError"))
    return MCPToolResult(
        ok=not is_error,
        text=text,
        content=items,
        error=text if is_error else "",
    )


class MCPClient:
    """Request-scoped client for a single MCP server. Use as an async context manager."""

    def __init__(self, config: MCPServerConfig, *, timeout: float = DEFAULT_TIMEOUT_SECONDS):
        config.validate()
        self.config = config
        self.timeout = timeout
        self._next_id = 0
        self._connected = False
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._http: Any = None
        self._session_id: str = ""

    async def __aenter__(self) -> "MCPClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        await self.close()

    def _request_id(self) -> int:
        self._next_id += 1
        return self._next_id

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> dict[str, Any]:
        if self._connected:
            return {}
        if self.config.transport == TRANSPORT_STDIO:
            await self._spawn_stdio()
        else:
            await self._open_http()

        result = await self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "clientInfo": CLIENT_INFO,
            },
        )
        await self._notify("notifications/initialized")
        self._connected = True
        return result if isinstance(result, dict) else {}

    async def close(self) -> None:
        self._connected = False
        proc, self._proc = self._proc, None
        if proc is not None:
            try:
                if proc.stdin is not None and not proc.stdin.is_closing():
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            except Exception:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        http, self._http = self._http, None
        if http is not None:
            try:
                await http.aclose()
            except Exception:
                pass

    # ── MCP methods ───────────────────────────────────────────────────────────

    async def list_tools(self) -> list[MCPTool]:
        await self.connect()
        result = await self._request("tools/list", {})
        raw_tools = (result or {}).get("tools") if isinstance(result, dict) else None
        if not isinstance(raw_tools, list):
            return []
        return [
            MCPTool.from_wire(t, server_id=self.config.id, server_name=self.config.name)
            for t in raw_tools
            if isinstance(t, dict) and t.get("name")
        ]

    async def call_tool(self, name: str, arguments: Optional[dict[str, Any]] = None) -> MCPToolResult:
        await self.connect()
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        if not isinstance(result, dict):
            return MCPToolResult(ok=True, text=str(result))
        return _normalize_call_result(result)

    # ── JSON-RPC plumbing ─────────────────────────────────────────────────────

    async def _request(self, method: str, params: dict[str, Any]) -> Any:
        message = {"jsonrpc": "2.0", "id": self._request_id(), "method": method, "params": params}
        try:
            if self.config.transport == TRANSPORT_STDIO:
                response = await asyncio.wait_for(
                    self._stdio_roundtrip(message), timeout=self.timeout
                )
            else:
                response = await asyncio.wait_for(
                    self._http_roundtrip(message), timeout=self.timeout
                )
        except asyncio.TimeoutError as exc:
            raise MCPError(f"MCP request '{method}' timed out after {self.timeout}s") from exc

        if not isinstance(response, dict):
            raise MCPError(f"Malformed MCP response for '{method}'")
        if response.get("error"):
            err = response["error"]
            detail = err.get("message") if isinstance(err, dict) else str(err)
            raise MCPError(f"MCP server error on '{method}': {detail}")
        return response.get("result")

    async def _notify(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        try:
            if self.config.transport == TRANSPORT_STDIO:
                await self._stdio_write(message)
            else:
                await self._http_post(message)
        except Exception:
            # Notifications are fire-and-forget; never fail a call because of them.
            pass

    # ── stdio transport ───────────────────────────────────────────────────────

    async def _spawn_stdio(self) -> None:
        env = {**os.environ, **{str(k): str(v) for k, v in (self.config.env or {}).items()}}
        try:
            self._proc = await asyncio.create_subprocess_exec(
                self.config.command,
                *[str(a) for a in (self.config.args or [])],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"MCP command not found: {self.config.command}") from exc
        except Exception as exc:
            raise MCPError(f"Failed to start MCP server: {exc}") from exc

    async def _stdio_write(self, message: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError("MCP stdio process is not running")
        self._proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _stdio_roundtrip(self, message: dict[str, Any]) -> dict[str, Any]:
        await self._stdio_write(message)
        if self._proc is None or self._proc.stdout is None:
            raise MCPError("MCP stdio process is not running")
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                raise MCPError("MCP server closed the connection")
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                # Servers sometimes log to stdout; ignore non-JSON noise.
                continue
            if isinstance(payload, dict) and payload.get("id") == message.get("id"):
                return payload

    # ── http / sse transport ──────────────────────────────────────────────────

    async def _open_http(self) -> None:
        import httpx

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update({str(k): str(v) for k, v in (self.config.env or {}).items()})
        self._http = httpx.AsyncClient(timeout=self.timeout, headers=headers)

    async def _http_post(self, message: dict[str, Any]) -> Any:
        if self._http is None:
            await self._open_http()
        headers = {"Mcp-Session-Id": self._session_id} if self._session_id else None
        try:
            return await self._http.post(self.config.url, json=message, headers=headers)
        except Exception as exc:
            raise MCPError(f"MCP HTTP request failed: {exc}") from exc

    async def _http_roundtrip(self, message: dict[str, Any]) -> dict[str, Any]:
        response = await self._http_post(message)
        session_id = response.headers.get("mcp-session-id") if response.headers else ""
        if session_id:
            self._session_id = session_id
        if response.status_code >= 400:
            raise MCPError(f"MCP HTTP {response.status_code}: {response.text[:200]}")

        content_type = (response.headers.get("content-type") or "").lower()
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if not line.startswith("data:"):
                    continue
                chunk = line[len("data:"):].strip()
                if not chunk:
                    continue
                try:
                    payload = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("id") == message.get("id"):
                    return payload
            raise MCPError("No JSON-RPC response found in SSE stream")

        try:
            return response.json()
        except Exception as exc:
            raise MCPError(f"Malformed JSON from MCP server: {exc}") from exc
