"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMNotConfiguredError(Exception):
    """Raised when no usable LLM provider/credentials are available."""


class LLMProvider(ABC):
    id: str

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
