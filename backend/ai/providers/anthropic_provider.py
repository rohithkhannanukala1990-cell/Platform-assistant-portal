"""Anthropic Messages API provider."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMNotConfiguredError, LLMProvider
from .openai_compatible import _mock_enabled, _mock_response


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
    ) -> str:
        if _mock_enabled():
            return _mock_response(messages)
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
        return "".join(texts) if texts else str(data)
