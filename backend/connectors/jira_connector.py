"""Jira connector."""

from __future__ import annotations

import asyncio
from typing import Any

from .registry import JiraConnector as _BaseJira


class JiraConnector(_BaseJira):
    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "ok": True,
            "tool": "jira",
            "action": action,
            "params": params,
            "message": f"Jira action '{action}' simulated",
        }
