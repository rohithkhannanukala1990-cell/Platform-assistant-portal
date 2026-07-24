"""OpenAI and OpenAI-compatible chat completions provider."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMNotConfiguredError, LLMProvider


def _mock_enabled() -> bool:
    return (os.getenv("LLM_MOCK") or "").strip().lower() in ("1", "true", "yes", "on")


def _mock_response(messages: List[Dict[str, Any]]) -> str:
    last = ""
    if messages:
        last = str(messages[-1].get("content") or "")
    return (
        f"[AI Mock] I received: '{last[:80]}...'\n"
        "Configure OPENAI_API_KEY or ANTHROPIC_API_KEY (or set LLM_MOCK=1) "
        "to enable responses."
    )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        provider_id: str = "openai",
    ):
        self.id = provider_id
        self._api_key = (api_key or "").strip()
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

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
                f"{self.id} API key is not configured (set OPENAI_API_KEY or LLM_MOCK=1)."
            )

        all_messages: List[Dict[str, Any]] = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        payload: Dict[str, Any] = {
            "model": model,
            "messages": all_messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]
