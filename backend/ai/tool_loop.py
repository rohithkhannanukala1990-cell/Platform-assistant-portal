"""Bounded LLM tool-use loop over MCP tools (Phase M1).

The model may request one tool per round; the loop runs at most ``max_rounds``
rounds. Tools are never invoked directly — every call goes through
:mod:`backend.mcp.hitl_bridge`, so auth, tenant scoping, allowlists, and HITL
approval all still apply. When a tool needs approval the loop stops and reports
the pending call instead of guessing an answer.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..auth import User
from ..mcp import hitl_bridge, registry
from ..observability.logger import logger
from .llm_service import llm_service

MAX_ROUNDS_DEFAULT = 3
_TOOL_BLOCK = re.compile(r"```(?:tool_call|json)?\s*(\{.*?\})\s*```", re.DOTALL)

_SYSTEM_TEMPLATE = """{base}

You can call external tools. To call one, reply with ONLY this fenced block:

```tool_call
{{"server_id": "<server_id>", "tool": "<tool name>", "arguments": {{}}}}
```

Rules:
- Call at most one tool per reply, and only when it is needed to answer.
- Use only the tools listed below, with their exact server_id and name.
- Tools marked "approval required" are queued for a human; do not assume they ran.
- When you have enough information, reply with the final answer in plain text.

Available tools:
{catalog}
"""


def _catalog_text(tools: list[dict[str, Any]]) -> str:
    lines = []
    for tool in tools:
        flag = " [approval required]" if tool.get("require_approval") else " [read-only]"
        description = (tool.get("description") or "").strip().replace("\n", " ")[:180]
        lines.append(
            f"- server_id={tool.get('server_id')} name={tool.get('name')}{flag}: {description}"
        )
    return "\n".join(lines) if lines else "(none)"


def _parse_tool_call(text: str) -> Optional[dict[str, Any]]:
    """Extract a tool request from a model reply, or None for a plain answer."""
    if not text:
        return None
    candidates = _TOOL_BLOCK.findall(text)
    if not candidates:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            candidates = [stripped]
    for raw in candidates:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        tool_name = str(payload.get("tool") or payload.get("name") or "").strip()
        server_id = str(payload.get("server_id") or payload.get("server") or "").strip()
        if not tool_name or not server_id:
            continue
        arguments = payload.get("arguments") or payload.get("args") or {}
        return {
            "server_id": server_id,
            "tool": tool_name,
            "arguments": arguments if isinstance(arguments, dict) else {},
        }
    return None


async def chat_with_tools(
    *,
    message: Optional[str] = None,
    messages: Optional[list[dict[str, Any]]] = None,
    user: Optional[User] = None,
    tenant_id: str = "default",
    max_rounds: int = MAX_ROUNDS_DEFAULT,
    use_mcp: bool = True,
    model: Optional[str] = None,
    system_prompt: str = "",
    source: str = "chat",
    ip_address: str = "",
) -> dict[str, Any]:
    """Run a bounded chat/tool loop and return the reply plus every call made."""
    history: list[dict[str, Any]] = list(messages or [])
    if message:
        history.append({"role": "user", "content": message})

    result: dict[str, Any] = {
        "reply": "",
        "rounds": 0,
        "tool_calls": [],
        "pending_approvals": [],
        "used_mcp": False,
        "tools_available": 0,
    }

    tools: list[dict[str, Any]] = []
    if use_mcp:
        try:
            tools, errors = await registry.list_all_tools(tenant_id)
            if errors:
                logger.warning("MCP tool discovery errors", extra={"source": "mcp", "count": len(errors)})
        except Exception as exc:
            logger.warning("MCP tool discovery failed", extra={"source": "mcp", "error": str(exc)})
            tools = []

    chat_user = ""
    if user is not None:
        chat_user = getattr(user, "username", None) or str(getattr(user, "id", "") or "")
    llm_attrs = {
        "user_id": chat_user or None,
        "tenant_id": tenant_id,
        "source": source or "chat",
    }

    result["tools_available"] = len(tools)
    if not tools:
        result["reply"] = await llm_service.chat(
            messages=history,
            model=model,
            system_prompt=system_prompt,
            **llm_attrs,
        )
        return result

    result["used_mcp"] = True
    loop_prompt = _SYSTEM_TEMPLATE.format(base=system_prompt or "", catalog=_catalog_text(tools))
    rounds = max(1, int(max_rounds or MAX_ROUNDS_DEFAULT))

    for _round in range(rounds):
        result["rounds"] += 1
        reply = await llm_service.chat(
            messages=history,
            model=model,
            system_prompt=loop_prompt,
            **llm_attrs,
        )
        requested = _parse_tool_call(reply)
        if requested is None:
            result["reply"] = reply
            return result

        history.append({"role": "assistant", "content": reply})
        try:
            call = await hitl_bridge.call_tool(
                server_id=requested["server_id"],
                tool_name=requested["tool"],
                arguments=requested["arguments"],
                user=user,
                tenant_id=tenant_id,
                source=source,
                ip_address=ip_address,
            )
        except Exception as exc:
            observation = f"Tool '{requested['tool']}' could not run: {exc}"
            history.append({"role": "user", "content": f"TOOL ERROR: {observation}"})
            continue

        result["tool_calls"].append(call)

        if call.get("status") == hitl_bridge.STATUS_PENDING:
            result["pending_approvals"].append(call)
            result["reply"] = (
                f"`{call['tool_name']}` on `{call['server_name']}` needs human approval "
                f"before it can run. Approval request `{call['id']}` is pending."
            )
            return result

        observation = json.dumps(call.get("result") or {}, default=str)[:4000]
        history.append(
            {"role": "user", "content": f"TOOL RESULT ({call['tool_name']}): {observation}"}
        )

    # Round budget exhausted — answer from what the tools already returned.
    result["reply"] = await llm_service.chat(
        messages=history,
        model=model,
        system_prompt=(system_prompt or "") + "\nAnswer now using the tool results above. Do not request more tools.",
        **llm_attrs,
    )
    return result
