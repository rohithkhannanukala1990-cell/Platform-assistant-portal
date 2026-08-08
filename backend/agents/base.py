"""Base agent types and shared execution / grounding helpers (Phase G2/P3)."""

from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

# Prompt discipline — agents must only reason over EVIDENCE blobs.
GROUNDING_RULES = """You must only use facts from the EVIDENCE section.
If evidence is empty, say you cannot assess and ask for connector setup.
Never invent metrics, PR numbers, pod names, ticket IDs, or repository names.
Return JSON when asked with keys: summary, findings, commands, residual_risk."""

VALID_GROUNDING = frozenset({"live", "partial", "none", "demo"})
MAX_COMMANDS_PER_RESULT = 25
MAX_EVIDENCE_CHARS = 30_000

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]+"),
    re.compile(r"(?i)ghp_[a-z0-9]{20,}"),
    re.compile(r"(?i)xox[baprs]-[a-z0-9-]{10,}"),
]


class AgentResult(BaseModel):
    agent: str
    status: str  # success | failed | pending_approval | dry_run | skipped
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
    # Phase G2 — structured quality bar
    evidence: list[dict] = Field(default_factory=list)
    confidence: Optional[float] = None
    grounding: str = "none"  # live | partial | none | demo
    policy: Optional[dict] = None
    errors: list[str] = Field(default_factory=list)
    recommended_actions: list[dict] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _process_env_is_production() -> bool:
    return (os.getenv("ENV") or "dev").strip().lower() in {"production", "prod", "dr"}


def redact_secret_like(text: str) -> str:
    out = str(text or "")
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def redact_structure(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secret_like(value)
    if isinstance(value, list):
        return [redact_structure(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_structure(v) for k, v in value.items()}
    return value


def truncate_evidence(evidence: list[dict] | None, *, max_chars: int = MAX_EVIDENCE_CHARS) -> list[dict]:
    """Cap serialized evidence size to avoid LLM context overflow."""
    rows = list(evidence or [])
    blob = json.dumps(rows, default=str)
    if len(blob) <= max_chars:
        return rows
    # Drop from the end until under budget; keep at least titles.
    trimmed: list[dict] = []
    size = 2
    for row in rows:
        piece = dict(row)
        snip = str(piece.get("snippet") or "")
        if len(snip) > 400:
            piece["snippet"] = snip[:400] + "…"
        candidate = json.dumps(piece, default=str)
        if size + len(candidate) + 1 > max_chars:
            break
        trimmed.append(piece)
        size += len(candidate) + 1
    return trimmed


class BaseAgent(ABC):
    name: str = "base_agent"
    description: str = ""
    requires_approval_envs: list[str] = []
    primary_tools: list[str] = []
    read_only: bool = False

    def _env_bucket(self, context: PlatformContext) -> str:
        env = (context.environment or "").strip().lower()
        if env in ("production", "prod", "dr") or _process_env_is_production():
            return "production"
        return env or "development"

    def _should_require_approval(self, context: PlatformContext) -> bool:
        env = self._env_bucket(context)
        return env in [e.lower() for e in self.requires_approval_envs] or (
            env == "production" and not self.read_only
        )

    def _is_prod_mutating(self, context: PlatformContext) -> bool:
        return (not self.read_only) and self._env_bucket(context) == "production"

    # ── Evidence / result factories ───────────────────────────────────────────

    def _evidence(
        self,
        *,
        type: str = "fact",
        title: str,
        source: str = "unknown",
        url: str | None = None,
        snippet: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "type": type,
            "title": title,
            "source": source,
        }
        if url:
            row["url"] = url
        if snippet is not None:
            row["snippet"] = redact_secret_like(str(snippet)[:2000])
        row.update(extra)
        return row

    def _result(
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
        evidence: Optional[list[dict]] = None,
        confidence: Optional[float] = None,
        grounding: str = "none",
        policy: Optional[dict] = None,
        errors: Optional[list[str]] = None,
        recommended_actions: Optional[list[dict]] = None,
    ) -> AgentResult:
        g = (grounding or "none").strip().lower()
        if g not in VALID_GROUNDING:
            g = "none"
        conf = confidence
        if conf is not None:
            conf = max(0.0, min(1.0, float(conf)))
        safe_details = redact_structure(details or {})
        if self.read_only and isinstance(safe_details, dict):
            safe_details["commands"] = []
        return AgentResult(
            agent=self.name,
            status=status,
            summary=redact_secret_like(summary),
            details=safe_details if isinstance(safe_details, dict) else {},
            requires_approval=requires_approval,
            approval_payload=redact_structure(approval_payload) if approval_payload else None,
            execution_log=redact_secret_like(execution_log) if execution_log else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
            triggered_by=context.user_id or "",
            workspace=context.workspace_id or "",
            environment=context.environment or "development",
            run_id=run_id,
            evidence=truncate_evidence(evidence),
            confidence=conf,
            grounding=g,
            policy=policy,
            errors=list(errors or []),
            recommended_actions=list(recommended_actions or []),
        )

    # Back-compat alias used by existing agents
    def _build_result(self, context: PlatformContext, **kwargs: Any) -> AgentResult:
        return self._result(context, **kwargs)

    def _no_data_result(
        self,
        context: PlatformContext,
        message: str,
        missing_tools: list[str] | None = None,
        *,
        details: Optional[dict] = None,
    ) -> AgentResult:
        tools = list(missing_tools or self.primary_tools[:1] or ["tool"])
        return self._result(
            context,
            status="skipped",
            summary=message,
            details={
                **(details or {}),
                "reason": "no_data",
                "missing_tools": tools,
                "connect_hint": "Connect the tool in Tool Registry, then retry.",
                "commands": [],
            },
            grounding="none",
            confidence=0.0,
            errors=[f"missing_tools:{','.join(tools)}"],
            recommended_actions=[
                {
                    "title": f"Connect {tools[0]} in Tool Registry",
                    "risk": "low",
                    "requires_approval": False,
                }
            ],
            evidence=[
                self._evidence(
                    type="connector",
                    title="No live connector data",
                    source="platform",
                    snippet=message,
                )
            ],
        )

    # ── Grounding connectors ──────────────────────────────────────────────────

    async def _ground_github(self, context: PlatformContext, session: Session | None = None):
        from ..services.github_access import try_github_connector_from_context

        return try_github_connector_from_context(context, db=session)

    async def _ground_k8s(self, context: PlatformContext, session: Session | None = None):
        from ..services.k8s_access import try_k8s_connector_from_context

        return try_k8s_connector_from_context(context, db=session)

    async def _ground_pd(self, context: PlatformContext, session: Session | None = None):
        from ..services.pagerduty_access import try_pagerduty_connector_from_context

        return try_pagerduty_connector_from_context(context, db=session)

    async def _ground_aws(self, context: PlatformContext, session: Session | None = None):
        """Resolve scoped AWS connector or return None if not configured."""
        from ..services.aws_access import try_aws_connector_from_context

        return try_aws_connector_from_context(context, db=session)

    # ── Policy ────────────────────────────────────────────────────────────────

    def _apply_command_policy(self, commands: list[str], context: PlatformContext):
        from ..services.command_policy import PolicyDecision, evaluate_commands

        cmds = [str(c) for c in (commands or []) if c][:MAX_COMMANDS_PER_RESULT]
        if not cmds:
            return PolicyDecision(effect="allow", reasons=["no commands"])
        return evaluate_commands(
            cmds,
            role=context.user_role or "User",
            environment=context.environment or "development",
            tool=context.active_tool or "shell",
            tenant_id=context.tenant_id,
        )

    def _policy_dict(self, decision) -> dict[str, Any]:
        if decision is None:
            return {}
        if hasattr(decision, "to_dict"):
            return decision.to_dict()
        return {
            "effect": getattr(decision, "effect", "allow"),
            "reasons": list(getattr(decision, "reasons", []) or []),
            "matched_rule_ids": list(getattr(decision, "matched_rule_ids", []) or []),
            "safe_for_auto": bool(getattr(decision, "safe_for_auto", True)),
        }

    def _cap_commands(self, commands: list[str] | None) -> list[str]:
        return [str(c) for c in (commands or []) if c][:MAX_COMMANDS_PER_RESULT]

    def _evidence_prompt(self, evidence: list[dict], task: str) -> str:
        rows = truncate_evidence(evidence)
        blob = json.dumps(rows, indent=2, default=str)
        if len(blob) > MAX_EVIDENCE_CHARS:
            blob = blob[: MAX_EVIDENCE_CHARS - 1] + "…"
        return (
            f"{GROUNDING_RULES}\n\n"
            f"Agent: {self.name}\n"
            f"Task: {task}\n\n"
            f"EVIDENCE:\n{blob}\n\n"
            "Respond with JSON: summary, findings (list), commands (list, may be empty), residual_risk."
        )

    def finalize_result(
        self,
        context: PlatformContext,
        *,
        summary: str,
        details: dict | None = None,
        commands: list[str] | None = None,
        evidence: list[dict] | None = None,
        grounding: str = "partial",
        confidence: float | None = None,
        task: str = "",
        recommended_actions: list[dict] | None = None,
        status: str | None = None,
        errors: list[str] | None = None,
    ) -> AgentResult:
        """
        Canonical finalize path (Phase P3).

        - Caps commands to 25 and redacts secret-like strings in details
        - Strips commands on deny / read_only
        - Forces requires_approval on require_approval or prod mutating
        """
        return self._finalize_with_policy(
            context,
            summary=summary,
            details=details or {},
            commands=list(commands or []),
            evidence=evidence,
            grounding=grounding,
            confidence=confidence,
            task=task,
            recommended_actions=recommended_actions,
            status_hint=status,
            errors=errors,
        )

    # ── LLM / execute ─────────────────────────────────────────────────────────

    async def _call_llm(
        self,
        prompt: str,
        context: PlatformContext,
        *,
        evidence: list[dict] | None = None,
    ) -> str:
        tools_hint = list(context.tool_accounts.keys()) or self.primary_tools
        mcp_block = ""
        try:
            from ..mcp.agent_mcp import format_mcp_catalog_for_prompt, mcp_enabled, mcp_tool_catalog

            if mcp_enabled():
                catalog = await mcp_tool_catalog(context.tenant_id)
                mcp_block = format_mcp_catalog_for_prompt(catalog)
        except Exception:
            logger.warning("MCP tool catalog unavailable; agent prompt continues without it", exc_info=True)
            mcp_block = ""

        system = llm_router.build_system_prompt(
            {
                "workspace_name": context.workspace_name or "default",
                "environment": context.environment,
                "tools": tools_hint,
                "production_operating": context.is_production() or _process_env_is_production(),
            }
        )
        system = (
            f"{system}\n\n{GROUNDING_RULES}\n"
            "Only reason over the EVIDENCE blob provided by the user message. "
            "If evidence is empty, say you cannot assess."
        )
        if mcp_block:
            system = f"{system}\n\n{mcp_block}"
        body = prompt
        if evidence is not None:
            body = self._evidence_prompt(evidence, prompt)
        elif GROUNDING_RULES not in (prompt or ""):
            body = f"{GROUNDING_RULES}\n\n{prompt}"
        messages = [{"role": "user", "content": body}]
        model = (os.getenv("LLM_DEFAULT_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        return await llm_router.chat(
            messages,
            model=model,
            system_prompt=system,
            user_id=getattr(context, "user_id", None),
            tenant_id=getattr(context, "tenant_id", None),
            workspace_id=getattr(context, "workspace_id", None),
            source=f"agent:{getattr(self, 'name', 'agent')}",
        )

    async def _execute(
        self, commands: list[str], context: PlatformContext, incident_id: int = 0
    ) -> dict[str, Any]:
        approved_by = context.user_id or "system"
        cmds = self._cap_commands(commands)
        policy_context = {
            "role": context.user_role,
            "environment": context.environment,
            "tool": context.active_tool or "shell",
            "tenant_id": context.tenant_id,
            "approved": False,
        }
        # Never auto-execute mutating commands in production without HITL approval.
        if self.read_only or not cmds or self._is_prod_mutating(context):
            preview = await safe_executor.dry_run(cmds or ["echo noop"], context=policy_context)
            return {"success": True, "dry_run": True, "logs": json.dumps(preview, indent=2)}
        return await safe_executor.execute(
            cmds, incident_id=incident_id, approved_by=approved_by, context=policy_context
        )

    def _parse_llm_json(self, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        # Extract first JSON object if model wrapped prose around it.
        if text and text[0] not in "{[":
            m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
            if m:
                text = m.group(1)
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return {"summary": str(data)[:500], "commands": [], "details": {}, "findings": []}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {"summary": (text or "")[:500], "commands": [], "details": {}, "findings": []}

    def _finalize_with_policy(
        self,
        context: PlatformContext,
        *,
        summary: str,
        details: dict,
        commands: list[str],
        evidence: list[dict] | None = None,
        grounding: str = "partial",
        confidence: float | None = None,
        task: str = "",
        recommended_actions: list[dict] | None = None,
        status_hint: str | None = None,
        errors: list[str] | None = None,
    ) -> AgentResult:
        """Apply command policy + HITL rules and return a consistent AgentResult."""
        cmds = self._cap_commands(commands)
        details = redact_structure({**(details or {}), "commands": cmds})
        needs_hitl = self._should_require_approval(context)
        policy_summary = None

        if self.read_only:
            # Never leave executable commands for the orchestrator auto-exec path.
            safe_details = {**(details or {}), "commands": []}
            return self._result(
                context,
                status=status_hint or "success",
                summary=summary,
                details=safe_details,
                evidence=evidence,
                grounding=grounding,
                confidence=confidence,
                recommended_actions=recommended_actions,
                errors=errors,
                execution_log="Read-only agent — no commands executed",
            )

        if cmds:
            decision = self._apply_command_policy(cmds, context)
            policy_summary = self._policy_dict(decision)
            if decision.effect == "deny":
                return self._result(
                    context,
                    status="failed",
                    summary="Command policy denied unsafe commands",
                    details={
                        **details,
                        "commands": [],
                        "policy_effect": "deny",
                        "policy_reasons": decision.reasons,
                    },
                    evidence=evidence,
                    grounding=grounding,
                    confidence=confidence,
                    policy=policy_summary,
                    errors=list(decision.reasons) + list(errors or []),
                    execution_log="; ".join(decision.reasons),
                )
            if decision.effect == "require_approval":
                needs_hitl = True

        if needs_hitl or (cmds and self._is_prod_mutating(context)):
            return self._result(
                context,
                status="pending_approval",
                summary=summary,
                details=details,
                requires_approval=True,
                approval_payload={"commands": cmds, "agent": self.name, "task": task},
                evidence=evidence,
                grounding=grounding,
                confidence=confidence,
                policy=policy_summary,
                recommended_actions=recommended_actions,
                errors=errors,
            )

        return self._result(
            context,
            status=status_hint or "success",
            summary=summary,
            details=details,
            evidence=evidence,
            grounding=grounding,
            confidence=confidence,
            policy=policy_summary,
            recommended_actions=recommended_actions,
            errors=errors,
        )

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        """Default path — LLM with empty evidence → grounding none (no invention)."""
        params = params if isinstance(params, dict) else {}
        if not (context.user_id or "").strip() and (os.getenv("ENV") or "").lower() not in (
            "test",
            "dev",
            "development",
            "local",
        ):
            return self._no_data_result(
                context,
                "user_id is required on PlatformContext",
                missing_tools=["identity"],
            )

        task = params.get("task") or params.get("message") or json.dumps(params)
        # Without live evidence, refuse to invent — subclasses must override with grounding.
        return self._no_data_result(
            context,
            f"{self.name} has no grounded evidence for this task. Connect tools or use a specialized agent path.",
            missing_tools=list(self.primary_tools) or ["evidence"],
            details={"task": str(task)[:300]},
        )
