"""OpenAI and OpenAI-compatible chat completions provider."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from .base import LLMNotConfiguredError, LLMProvider


def _mock_enabled() -> bool:
    return (os.getenv("LLM_MOCK") or "").strip().lower() in ("1", "true", "yes", "on")


def _mock_postmortem_response(messages: List[Dict[str, Any]]) -> str | None:
    """Deterministic postmortem sections when POSTMORTEM_GENERATION_V1 is in the prompt."""
    import json
    import re

    blob = "\n".join(str(m.get("content") or "") for m in messages)
    if "POSTMORTEM_GENERATION_V1" not in blob and "INCIDENT_CONTEXT_JSON" not in blob:
        return None

    ctx: dict = {}
    m = re.search(r"INCIDENT_CONTEXT_JSON:\s*(\{.*\})\s*$", blob, re.DOTALL)
    if m:
        try:
            ctx = json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError, ValueError):
            ctx = {}

    summary = ctx.get("summary") or "Mock incident summary."
    severity = ctx.get("severity") or "Medium"
    status = ctx.get("status") or "OPEN"
    root_cause = ctx.get("root_cause") or "Mock root cause from triage data."
    source = ctx.get("source") or "manual"
    ts = ctx.get("timestamp") or "unknown"
    evidence = ctx.get("evidence") or []
    action_plan = ctx.get("action_plan") or []
    timeline = ctx.get("timeline") or []

    timeline_lines = []
    for ev in timeline:
        timeline_lines.append(
            f"- **{ev.get('type', 'event')}** ({ev.get('at', '—')}) "
            f"— {ev.get('actor', 'system')}: {ev.get('detail', '')}"
        )
    timeline_body = "\n".join(timeline_lines) if timeline_lines else "No timeline events recorded."

    evidence_line = evidence[0] if evidence else "No evidence captured."
    actions = "\n".join(f"- {a}" for a in action_plan[:3]) or "- Review monitoring and add runbook coverage."

    return f"""## Summary

{summary}

## Impact

Severity **{severity}**; incident status **{status}**. Impact inferred from triage summary and evidence.

## Detection

Detected via **{source}** at {ts}. Supporting signal: {evidence_line}

## Root cause

{root_cause}

## What went well

Automated triage produced structured evidence and an action plan for operators.

## What went wrong

Response required manual intervention; gaps noted in validation and follow-up coverage.

## Action items

{actions}

## Timeline

{timeline_body}
"""


def _mock_response(messages: List[Dict[str, Any]]) -> str:
    postmortem = _mock_postmortem_response(messages)
    if postmortem is not None:
        return postmortem

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
