"""GitHub connector — test_connection + execute_action."""

from __future__ import annotations

import asyncio
from typing import Any

from .registry import GitHubConnector as _BaseGitHub


class GitHubConnector(_BaseGitHub):
    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "ok": True,
            "tool": "github",
            "action": action,
            "params": params,
            "message": f"GitHub action '{action}' simulated",
        }
