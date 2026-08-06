"""Anthropic Messages API provider."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMChatResult, LLMNotConfiguredError, LLMProvider
from .openai_compatible import _mock_enabled, _mock_response
from ..usage_pricing import estimate_tokens_from_text


class AnthropicProvider(LLMProvider):
    id = "anthropic"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com"):
        self._api_key = (api_key or "").strip()
        self._base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    async def is_available(self) -> bool:
        if _mock_enabled():
            return True
        return bool(self._api_key)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMChatResult:
        if _mock_enabled():
            text = _mock_response(messages)
            prompt_est = estimate_tokens_from_text(
                (system_prompt or "")
                + "\n".join(str(m.get("content") or "") for m in messages)
            )
            completion_est = estimate_tokens_from_text(text)
            return LLMChatResult(
                text=text,
                prompt_tokens=prompt_est,
                completion_tokens=completion_est,
                total_tokens=prompt_est + completion_est,
                provider=self.id,
                model=model,
            )
        if not self._api_key:
            raise LLMNotConfiguredError(
                "anthropic API key is not configured (set ANTHROPIC_API_KEY or LLM_MOCK=1)."
            )

        # Anthropic expects alternating user/assistant; system is separate.
        api_messages: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role") or "user"
            if role == "system":
                continue
            if role not in ("user", "assistant"):
                role = "user"
            api_messages.append({"role": role, "content": m.get("content") or ""})

        payload: Dict[str, Any] = {
            "model": model,
            "messages": api_messages or [{"role": "user", "content": ""}],
            "max_tokens": max_tokens if max_tokens is not None else 2048,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/v1/messages"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        parts = data.get("content") or []
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"]
        text = "".join(texts) if texts else str(data)
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("input_tokens") or 0)
        completion_tokens = int(usage.get("output_tokens") or 0)
        return LLMChatResult(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            provider=self.id,
            model=model,
        )
