"""PagerDuty connector."""

from __future__ import annotations

import asyncio
from typing import Any

from .registry import PagerDutyConnector as _BasePd


class PagerDutyConnector(_BasePd):
    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        await asyncio.sleep(0.05)
        return {
            "ok": True,
            "tool": "pagerduty",
            "action": action,
            "params": params,
            "message": f"PagerDuty action '{action}' simulated",
        }
