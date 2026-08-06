"""Thin shim — delegates to llm_service (kept for existing imports/patches)."""

from __future__ import annotations

from typing import Dict, List, Optional

from .llm_service import llm_service
from .providers import LLMNotConfiguredError


class LLMRouter:
    def get_provider(self, model: str) -> str:
        provider, _ = llm_service.resolve_provider_and_model(model=model)
        return provider

    async def chat(
        self,
        messages: List[Dict],
        model: Optional[str] = None,
        system_prompt: str = "",
        stream: bool = False,
        provider: Optional[str] = None,
        *,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        source: str = "unknown",
    ) -> str:
        _ = stream  # streaming not implemented in L1
        return await llm_service.chat(
            messages=messages,
            model=model,
            provider=provider,
            system_prompt=system_prompt,
            user_id=user_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            source=source,
        )

    def build_system_prompt(self, context: dict) -> str:
        return llm_service.build_system_prompt(context)


llm_router = LLMRouter()

__all__ = ["LLMRouter", "llm_router", "LLMNotConfiguredError"]
