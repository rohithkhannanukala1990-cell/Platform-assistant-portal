"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class LLMNotConfiguredError(Exception):
    """Raised when no usable LLM provider/credentials are available."""


@dataclass
class LLMChatResult:
    """Provider response with optional token usage."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    provider: str = ""
    model: str = ""

    def __str__(self) -> str:
        return self.text


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
    ) -> LLMChatResult:
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...
