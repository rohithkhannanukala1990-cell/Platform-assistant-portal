"""Base agent types and shared execution helpers."""

from __future__ import annotations

import json
import os
import re
from abc import ABC
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlmodel import Session

from ..ai.llm_router import llm_router
from ..command_validator import CommandValidator
from ..context import PlatformContext
from ..executor.safe_executor import safe_executor


class AgentResult(BaseModel):
    agent: str
    status: str  # success | failed | pending_approval | dry_run
    summary: str
    details: dict = Field(default_factory=dict)
    requires_approval: bool = False
    approval_payload: Optional[dict] = None
    execution_log: Optional[str] = None
    timestamp: str
    triggered_by: str
    workspace: str
    environment: str
    run_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class BaseAgent(ABC):
    name: str = "base_agent"
    description: str = ""
    requires_approval_envs: list[str] = []
    primary_tools: list[str] = []
    read_only: bool = False

    def _should_require_approval(self, context: PlatformContext) -> bool:
        env = (context.environment or "").strip().lower()
        if env in ("production", "prod", "dr"):
            env = "production"
        return env in [e.lower() for e in self.requires_approval_envs]

    async def _call_llm(self, prompt: str, context: PlatformContext) -> str:
        system = llm_router.build_system_prompt(
            {
                "workspace_name": context.workspace_name or "default",
                "environment": context.environment,
                "tools": list(context.tool_accounts.keys()) or self.primary_tools,
                "production_operating": context.is_production(),
            }
        )
        messages = [{"role": "user", "content": prompt}]
        model = (os.getenv("LLM_DEFAULT_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        return await llm_router.chat(messages, model=model, system_prompt=system)

    async def _execute(
        self, commands: list[str], context: PlatformContext, incident_id: int = 0
    ) -> dict[str, Any]:
        approved_by = context.user_id or "system"
        if self.read_only or not commands:
            preview = await safe_executor.dry_run(commands or ["echo noop"])
            return {"success": True, "dry_run": True, "logs": json.dumps(preview, indent=2)}
        return await safe_executor.execute(commands, incident_id=incident_id, approved_by=approved_by)

    def _parse_llm_json(self, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"summary": text[:500], "commands": [], "details": {}}

    def _build_result(
        self,
        context: PlatformContext,
        *,
        status: str,
        summary: str,
        details: Optional[dict] = None,
        requires_approval: bool = False,
        approval_payload: Optional[dict] = None,
        execution_log: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> AgentResult:
        return AgentResult(
            agent=self.name,
            status=status,
            summary=summary,
            details=details or {},
            requires_approval=requires_approval,
            approval_payload=approval_payload,
            execution_log=execution_log,
            timestamp=datetime.now(timezone.utc).isoformat(),
            triggered_by=context.user_id,
            workspace=context.workspace_id,
            environment=context.environment,
            run_id=run_id,
        )

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        task = params.get("task") or params.get("message") or json.dumps(params)
        prompt = (
            f"You are {self.name}. {self.description}\n"
            f"Environment: {context.environment}\n"
            f"Workspace: {context.workspace_name}\n"
            f"Params: {json.dumps(params)}\n"
            f"Task: {task}\n"
            "Return JSON with keys: summary (string), commands (list of shell commands, may be empty), "
            "details (object with findings), requires_approval (bool)."
        )
        raw = await self._call_llm(prompt, context)
        parsed = self._parse_llm_json(raw)
        summary = str(parsed.get("summary") or f"{self.name} completed analysis")
        commands = [str(c) for c in (parsed.get("commands") or []) if c]
        details = parsed.get("details") if isinstance(parsed.get("details"), dict) else {"raw": parsed}

        needs_hitl = self._should_require_approval(context) or bool(parsed.get("requires_approval"))
        if self.read_only:
            return self._build_result(
                context,
                status="success",
                summary=summary,
                details=details,
                execution_log="Read-only agent — no commands executed",
            )

        if commands:
            check = CommandValidator.validate(commands)
            if not check.safe:
                return self._build_result(
                    context,
                    status="failed",
                    summary="Command validation blocked unsafe commands",
                    details={"violations": check.violations, **details},
                    execution_log=str(check.violations),
                )

        if needs_hitl:
            return self._build_result(
                context,
                status="pending_approval",
                summary=summary,
                details={**details, "commands": commands},
                requires_approval=True,
                approval_payload={"commands": commands, "agent": self.name, "task": task},
            )

        exec_out = await self._execute(commands, context)
        status = "success" if exec_out.get("success") else "failed"
        return self._build_result(
            context,
            status=status,
            summary=summary,
            details={**details, "commands": commands, "execution": exec_out},
            execution_log=exec_out.get("logs"),
        )
