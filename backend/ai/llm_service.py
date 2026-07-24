"""Multi-provider LLM service — single entry point for chat."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .providers import (
    AnthropicProvider,
    LLMNotConfiguredError,
    OpenAICompatibleProvider,
)
from .providers.openai_compatible import _mock_enabled


class LLMService:
    def build_system_prompt(self, context: dict) -> str:
        workspace = context.get("workspace_name", "None")
        environment = context.get("environment", "production")
        tools = context.get("tools", [])
        tool_list = ", ".join(tools) if tools else "none"
        base = f"""You are an AI assistant embedded in
Platform Assistant Portal, an internal developer platform.

Current context:
- Active Workspace: {workspace}
- Environment: {environment}
- Connected Tools: {tool_list}

You help engineers with:
- Checking tool health and connectivity
- Explaining infrastructure state
- Drafting runbooks and incident responses
- Summarizing alerts and metrics
- Suggesting workspace configurations

For actions that modify production systems,
always ask for confirmation before proceeding.
High-risk actions (HITL required) must be
explicitly approved by the user.

Be concise, technical, and accurate."""
        extra = ""
        ts = (context.get("tool_statuses_line") or "").strip()
        if ts:
            extra += f"\n\nTool statuses: {ts}"
        if context.get("production_operating"):
            extra += (
                "\n\n⚠️ You are operating in PRODUCTION.\n"
                "Treat all destructive actions as HITL-required."
            )
        extra += (
            "\n\nWhen you propose actions, ALWAYS produce a separate JSON block "
            "labeled 'ACTIONS_JSON' with this format:\n"
            "ACTIONS_JSON: { \"actions\": [ { \"resource\": \"service\", "
            "\"operation\": \"restart\", \"environment\": \"production\", "
            "\"identifier\": \"svc-name\", \"reason\": \"...\" } ] }\n"
            "Keep this JSON strictly valid. Do not include comments or extra "
            "text inside the JSON."
        )
        return base + extra

    def get_status(self) -> dict:
        openai_key = bool((os.getenv("OPENAI_API_KEY") or "").strip())
        anthropic_key = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
        base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        default_provider = (os.getenv("LLM_DEFAULT_PROVIDER") or "openai").strip() or "openai"
        default_model = (os.getenv("LLM_DEFAULT_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"
        return {
            "default_provider": default_provider,
            "default_model": default_model,
            "openai_configured": openai_key,
            "anthropic_configured": anthropic_key,
            "openai_base_url": base_url,
            "mock": _mock_enabled(),
            "providers": ["openai", "openai_compatible", "anthropic"],
        }

    def _infer_provider_from_model(self, model: str) -> Optional[str]:
        m = (model or "").strip().lower()
        if not m:
            return None
        if m.startswith("claude"):
            return "anthropic"
        if m.startswith("gpt") or m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
            return "openai"
        return None

    def resolve_provider_and_model(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> tuple[str, str]:
        explicit_provider = (provider or "").strip().lower() or None
        explicit_model = (model or "").strip() or None

        env_provider = (os.getenv("LLM_DEFAULT_PROVIDER") or "").strip().lower() or None
        env_model = (os.getenv("LLM_DEFAULT_MODEL") or "").strip() or None

        openai_key = bool((os.getenv("OPENAI_API_KEY") or "").strip())
        anthropic_key = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())

        resolved_provider = explicit_provider
        resolved_model = explicit_model

        if not resolved_provider and resolved_model:
            resolved_provider = self._infer_provider_from_model(resolved_model)

        if not resolved_provider:
            resolved_provider = env_provider
        if not resolved_model:
            resolved_model = env_model

        if not resolved_provider:
            if openai_key:
                resolved_provider = "openai"
            elif anthropic_key:
                resolved_provider = "anthropic"
            elif _mock_enabled():
                resolved_provider = env_provider or "openai"
            else:
                raise LLMNotConfiguredError(
                    "No LLM configured. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or LLM_MOCK=1."
                )

        if not resolved_model:
            if resolved_provider == "anthropic":
                resolved_model = "claude-3-5-haiku-latest"
            else:
                resolved_model = "gpt-4o-mini"

        return resolved_provider, resolved_model

    def _build_provider(self, provider_id: str) -> OpenAICompatibleProvider | AnthropicProvider:
        pid = (provider_id or "").strip().lower()
        if pid == "anthropic":
            return AnthropicProvider(api_key=os.getenv("ANTHROPIC_API_KEY") or "")
        if pid in ("openai", "openai_compatible"):
            base = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            return OpenAICompatibleProvider(
                api_key=os.getenv("OPENAI_API_KEY") or "",
                base_url=base,
                provider_id=pid,
            )
        raise LLMNotConfiguredError(
            f"Unknown LLM provider '{provider_id}'. Supported: openai, openai_compatible, anthropic."
        )

    async def chat(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        prompt: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        if messages is None:
            messages = []
        if prompt:
            messages = list(messages) + [{"role": "user", "content": prompt}]
        if not messages:
            raise ValueError("chat requires messages or prompt")

        provider_id, resolved_model = self.resolve_provider_and_model(model=model, provider=provider)
        impl = self._build_provider(provider_id)
        return await impl.chat(
            messages,
            model=resolved_model,
            system_prompt=system_prompt or "",
            temperature=temperature,
            max_tokens=max_tokens,
        )


llm_service = LLMService()
