"""Platform execution context passed through the agent pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

_DEV_ENVIRONMENTS = frozenset({"dev", "development", "test", "local"})
_PROD_ENVIRONMENTS = frozenset({"production", "prod", "dr"})


@dataclass
class PlatformContext:
    request_id: str = ""
    workspace_id: str = ""
    workspace_name: str = ""
    environment: str = "development"
    tool_accounts: dict[str, str] = field(default_factory=dict)
    user_id: str = ""
    user_role: str = "User"
    active_tool: Optional[str] = None
    active_account: Optional[str] = None

    @staticmethod
    def current_env() -> str:
        return (os.getenv("ENV") or "dev").strip().lower()

    @classmethod
    def is_dev_environment(cls) -> bool:
        return cls.current_env() in _DEV_ENVIRONMENTS

    def is_production(self) -> bool:
        return (self.environment or "").strip().lower() in _PROD_ENVIRONMENTS

    def is_dev(self) -> bool:
        return (self.environment or "").strip().lower() in _DEV_ENVIRONMENTS

    def get_account(self, tool_id: str) -> Optional[str]:
        return self.tool_accounts.get(tool_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "environment": self.environment,
            "tool_accounts": dict(self.tool_accounts),
            "user_id": self.user_id,
            "user_role": self.user_role,
            "active_tool": self.active_tool,
            "active_account": self.active_account,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], user_id: str = "", user_role: str = "User") -> "PlatformContext":
        env = (data.get("environment") or "development").strip().lower()
        accounts = data.get("tool_accounts") or {}
        if not isinstance(accounts, dict):
            accounts = {}
        return cls(
            request_id=str(data.get("request_id") or ""),
            workspace_id=str(data.get("workspace_id") or ""),
            workspace_name=str(data.get("workspace_name") or ""),
            environment=env,
            tool_accounts={str(k): str(v) for k, v in accounts.items()},
            user_id=str(data.get("user_id") or user_id),
            user_role=str(data.get("user_role") or user_role),
            active_tool=data.get("active_tool"),
            active_account=data.get("active_account"),
        )
