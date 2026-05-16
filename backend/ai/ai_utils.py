"""Shared AI utility — provider-agnostic ask function."""

from __future__ import annotations

import os

import ollama
from dotenv import load_dotenv
from google import genai

from ..observability.logger import logger

load_dotenv()

# Default to Ollama so callers can run without cloud credentials.
AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama").lower()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")

DEFAULT_SYSTEM_PROMPT = """You are a senior DevOps and SRE engineer embedded inside Cursor IDE.
Analyze the provided server logs and return ONLY a valid JSON object — no markdown, no explanation, no code fences.

The JSON must have exactly these keys:

{
  "severity": "<Critical | High | Medium | Low>",
  "summary": "<One sentence describing what is broken and the immediate impact.>",
  "root_cause": "<2-4 sentences. State the failing component, the technical reason it failed, and blast radius. Reference specific error codes or service names from the logs. Do not restate the logs — explain WHY.>",
  "evidence": [
    "<Specific log line or pattern that proves the root cause>",
    "<Another supporting log entry>"
  ],
  "action_plan": [
    "Immediate: <One action to stop active damage right now with the exact command or config change.>",
    "Fix: <The permanent code, config, or infra change — specify the file and what to change.>",
    "Harden: <One monitoring or alerting improvement to prevent recurrence.>"
  ],
  "commands": [
    "<exact shell command 1>",
    "<exact shell command 2>"
  ],
  "files_to_check": [
    "<file path or k8s resource> (<reason>)",
    "<file path or k8s resource> (<reason>)"
  ],
  "validation_steps": [
    "<Exact command or log pattern to confirm the fix worked>",
    "<Metric or threshold to verify system health>"
  ]
}

Rules:
- Use real inferred values from the logs. Do not use placeholder strings like <namespace> or <your-service>.
- The commands array must contain runnable shell/kubectl/psql/docker commands only — no prose.
- Return ONLY the JSON object. Nothing before or after it."""

gemini_client = None
if AI_PROVIDER == "gemini":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set - falling back to ollama")
        AI_PROVIDER = "ollama"
    else:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)


async def call_ollama(logs: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": logs},
        ],
    )
    return response.message.content


async def call_gemini(logs: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> str:
    prompt = f"{system_prompt}\n\nLogs to analyze:\n{logs}"
    result = gemini_client.models.generate_content(
        model="gemma-3-27b-it",
        contents=prompt,
    )
    return result.text


async def ask_ai(prompt: str) -> str:
    if AI_PROVIDER == "ollama":
        return await call_ollama(prompt)
    return await call_gemini(prompt)
