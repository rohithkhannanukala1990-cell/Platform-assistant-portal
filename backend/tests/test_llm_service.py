"""Phase L1 — multi-provider LLMService."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.ai.llm_service import llm_service
from backend.ai.providers import LLMNotConfiguredError


def test_llm_mock_chat_works(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    text = asyncio.run(
        llm_service.chat(
            messages=[{"role": "user", "content": "hello phase L1"}],
            system_prompt="be brief",
        )
    )
    assert "AI Mock" in text
    assert "hello phase L1" in text


def test_llm_raises_when_not_configured(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_DEFAULT_PROVIDER", raising=False)
    with pytest.raises(LLMNotConfiguredError):
        asyncio.run(llm_service.chat(prompt="ping"))


def test_ai_utils_has_no_gemini_or_ollama_imports():
    src = Path(__file__).resolve().parents[1] / "ai" / "ai_utils.py"
    text = src.read_text(encoding="utf-8")
    assert "import ollama" not in text
    assert "call_gemini" not in text
    assert "google.genai" not in text
    assert "from google" not in text


def test_build_system_prompt_includes_actions_json():
    prompt = llm_service.build_system_prompt(
        {
            "workspace_name": "ws",
            "environment": "production",
            "tools": ["github"],
            "production_operating": True,
        }
    )
    assert "ACTIONS_JSON" in prompt
    assert "PRODUCTION" in prompt
