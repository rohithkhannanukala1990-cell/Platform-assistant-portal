"""AWS connector."""

from __future__ import annotations

import asyncio
from typing import Any

from .registry import AWSConnector as _BaseAws


class AWSConnector(_BaseAws):
    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "ok": True,
            "tool": "aws",
            "action": action,
            "params": params,
            "message": f"AWS action '{action}' simulated",
        }
