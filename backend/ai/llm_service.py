"""Multi-provider LLM service — single entry point for chat."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlmodel import Session, col, select

from .providers import (
    AnthropicProvider,
    LLMNotConfiguredError,
    OpenAICompatibleProvider,
)
from .providers.openai_compatible import _mock_enabled


@dataclass
class _ResolvedLLM:
    provider: str
    model: str
    api_key: str = ""
    base_url: Optional[str] = None
    source: str = "env"
    config_id: Optional[int] = None


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

    def _list_db_rows(self, *, active_only: bool = False) -> list:
        try:
            from ..auth import LLMProviderConfig, engine
        except Exception:
            return []
        try:
            with Session(engine) as session:
                stmt = select(LLMProviderConfig)
                if active_only:
                    stmt = stmt.where(LLMProviderConfig.is_active == True)  # noqa: E712
                stmt = stmt.order_by(
                    col(LLMProviderConfig.priority).desc(),
                    col(LLMProviderConfig.updated_at).desc(),
                )
                return list(session.exec(stmt).all())
        except Exception:
            return []

    def _mask_db_row(self, row) -> dict[str, Any]:
        return {
            "id": row.id,
            "provider": row.provider,
            "model_name": row.model_name,
            "base_url": row.base_url,
            "has_api_key": bool((row.api_key_vault_ref or "").strip()),
            "fallback_provider": row.fallback_provider,
            "fallback_model": row.fallback_model,
            "monthly_token_budget": row.monthly_token_budget,
            "tokens_used_this_month": row.tokens_used_this_month,
            "is_active": row.is_active,
            "priority": int(getattr(row, "priority", 0) or 0),
            "metadata_json": getattr(row, "metadata_json", None) or "{}",
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }

    def get_status(self) -> dict:
        openai_key = bool((os.getenv("OPENAI_API_KEY") or "").strip())
        anthropic_key = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())
        base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        default_provider = (os.getenv("LLM_DEFAULT_PROVIDER") or "openai").strip() or "openai"
        default_model = (os.getenv("LLM_DEFAULT_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"

        db_rows = self._list_db_rows(active_only=False)
        active = [r for r in db_rows if r.is_active]
        if active:
            top = active[0]
            default_provider = (top.provider or default_provider).strip() or default_provider
            default_model = (top.model_name or default_model).strip() or default_model

        models: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in active:
            mid = (row.model_name or "").strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            models.append(
                {
                    "id": mid,
                    "provider": row.provider,
                    "available": True,
                    "label": f"{mid} ({row.provider})",
                    "config_id": row.id,
                }
            )
        # Fallback catalog when no active DB models
        if not models:
            mock = _mock_enabled()
            for mid, provider, label in (
                ("gpt-4o-mini", "openai", "GPT-4o mini (OpenAI)"),
                ("gpt-4o", "openai", "GPT-4o (OpenAI)"),
                ("claude-3-5-haiku-latest", "anthropic", "Claude 3.5 Haiku (Anthropic)"),
                ("claude-3-5-sonnet-latest", "anthropic", "Claude 3.5 Sonnet (Anthropic)"),
            ):
                avail = mock or (openai_key if provider == "openai" else anthropic_key)
                models.append(
                    {
                        "id": mid,
                        "provider": provider,
                        "available": avail,
                        "label": label,
                        "config_id": None,
                    }
                )

        return {
            "default_provider": default_provider,
            "default_model": default_model,
            "openai_configured": openai_key or any(
                r.provider in ("openai", "openai_compatible") and (r.api_key_vault_ref or "").strip()
                for r in active
            ),
            "anthropic_configured": anthropic_key
            or any(r.provider == "anthropic" and (r.api_key_vault_ref or "").strip() for r in active),
            "openai_base_url": base_url,
            "mock": _mock_enabled(),
            "providers": [self._mask_db_row(r) for r in db_rows],
            "models": models,
            "supported_providers": ["openai", "openai_compatible", "anthropic"],
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

    def _decrypt_row_key(self, row) -> str:
        ref = (row.api_key_vault_ref or "").strip()
        if not ref:
            return ""
        try:
            from ..services.secrets import decrypt_secret

            return decrypt_secret(ref) or ""
        except Exception:
            return ""

    def _env_key_for(self, provider: str) -> str:
        pid = (provider or "").strip().lower()
        if pid == "anthropic":
            return (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        return (os.getenv("OPENAI_API_KEY") or "").strip()

    def _env_base_url(self, provider: str, override: Optional[str] = None) -> Optional[str]:
        if override and str(override).strip():
            return str(override).strip()
        pid = (provider or "").strip().lower()
        if pid in ("openai", "openai_compatible"):
            return (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").strip()
        return None

    def _credentials_for_provider(self, provider: str) -> tuple[str, Optional[str], Optional[int]]:
        """Return (api_key, base_url, config_id) from highest-priority matching DB row or env."""
        pid = (provider or "").strip().lower()
        for row in self._list_db_rows(active_only=True):
            if (row.provider or "").strip().lower() == pid:
                key = self._decrypt_row_key(row)
                if key or _mock_enabled():
                    return key, self._env_base_url(pid, row.base_url), row.id
        return self._env_key_for(pid), self._env_base_url(pid), None

    def _resolve(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        config_id: Optional[int] = None,
    ) -> _ResolvedLLM:
        # Explicit config id (admin test)
        if config_id is not None:
            from ..auth import LLMProviderConfig, engine

            with Session(engine) as session:
                row = session.get(LLMProviderConfig, config_id)
                if not row:
                    raise LLMNotConfiguredError(f"LLM provider config id={config_id} not found")
                return _ResolvedLLM(
                    provider=(row.provider or "openai").strip().lower(),
                    model=(row.model_name or "gpt-4o-mini").strip(),
                    api_key=self._decrypt_row_key(row),
                    base_url=self._env_base_url(row.provider, row.base_url),
                    source="db",
                    config_id=row.id,
                )

        explicit_provider = (provider or "").strip().lower() or None
        explicit_model = (model or "").strip() or None
        env_provider = (os.getenv("LLM_DEFAULT_PROVIDER") or "").strip().lower() or None
        env_model = (os.getenv("LLM_DEFAULT_MODEL") or "").strip() or None

        # 1) explicit args
        if explicit_provider or explicit_model:
            resolved_provider = explicit_provider or self._infer_provider_from_model(explicit_model or "")
            if not resolved_provider:
                resolved_provider = env_provider or "openai"
            resolved_model = explicit_model or env_model
            if not resolved_model:
                resolved_model = (
                    "claude-3-5-haiku-latest" if resolved_provider == "anthropic" else "gpt-4o-mini"
                )
            key, base, cid = self._credentials_for_provider(resolved_provider)
            return _ResolvedLLM(
                provider=resolved_provider,
                model=resolved_model,
                api_key=key,
                base_url=base,
                source="explicit",
                config_id=cid,
            )

        # 2) env defaults
        if env_provider or env_model:
            resolved_provider = env_provider or self._infer_provider_from_model(env_model or "") or "openai"
            resolved_model = env_model or (
                "claude-3-5-haiku-latest" if resolved_provider == "anthropic" else "gpt-4o-mini"
            )
            key, base, cid = self._credentials_for_provider(resolved_provider)
            return _ResolvedLLM(
                provider=resolved_provider,
                model=resolved_model,
                api_key=key,
                base_url=base,
                source="env",
                config_id=cid,
            )

        # 3) highest priority active DB row
        active = self._list_db_rows(active_only=True)
        if active:
            row = active[0]
            return _ResolvedLLM(
                provider=(row.provider or "openai").strip().lower(),
                model=(row.model_name or "gpt-4o-mini").strip(),
                api_key=self._decrypt_row_key(row),
                base_url=self._env_base_url(row.provider, row.base_url),
                source="db",
                config_id=row.id,
            )

        # 4) env API keys
        if (os.getenv("OPENAI_API_KEY") or "").strip():
            return _ResolvedLLM(
                provider="openai",
                model="gpt-4o-mini",
                api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
                base_url=self._env_base_url("openai"),
                source="env_key",
            )
        if (os.getenv("ANTHROPIC_API_KEY") or "").strip():
            return _ResolvedLLM(
                provider="anthropic",
                model="claude-3-5-haiku-latest",
                api_key=(os.getenv("ANTHROPIC_API_KEY") or "").strip(),
                base_url=None,
                source="env_key",
            )

        # 5) mock
        if _mock_enabled():
            return _ResolvedLLM(
                provider="openai",
                model="gpt-4o-mini",
                api_key="",
                base_url=self._env_base_url("openai"),
                source="mock",
            )

        # 6) error
        raise LLMNotConfiguredError(
            "No LLM configured. Add an active provider in /api/llm, set OPENAI_API_KEY / "
            "ANTHROPIC_API_KEY, or LLM_MOCK=1."
        )

    def resolve_provider_and_model(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> tuple[str, str]:
        resolved = self._resolve(model=model, provider=provider)
        return resolved.provider, resolved.model

    def _build_provider(
        self,
        provider_id: str,
        *,
        api_key: str = "",
        base_url: Optional[str] = None,
    ) -> OpenAICompatibleProvider | AnthropicProvider:
        pid = (provider_id or "").strip().lower()
        key = (api_key or "").strip()
        if pid == "anthropic":
            return AnthropicProvider(api_key=key or self._env_key_for("anthropic"))
        if pid in ("openai", "openai_compatible"):
            base = base_url or self._env_base_url(pid)
            return OpenAICompatibleProvider(
                api_key=key or self._env_key_for("openai"),
                base_url=base or "https://api.openai.com/v1",
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
        config_id: Optional[int] = None,
    ) -> str:
        if messages is None:
            messages = []
        if prompt:
            messages = list(messages) + [{"role": "user", "content": prompt}]
        if not messages:
            raise ValueError("chat requires messages or prompt")

        resolved = self._resolve(model=model, provider=provider, config_id=config_id)
        impl = self._build_provider(
            resolved.provider,
            api_key=resolved.api_key,
            base_url=resolved.base_url,
        )
        return await impl.chat(
            messages,
            model=resolved.model,
            system_prompt=system_prompt or "",
            temperature=temperature,
            max_tokens=max_tokens,
        )


llm_service = LLMService()
