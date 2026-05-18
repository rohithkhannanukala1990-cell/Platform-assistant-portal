"""Classify free-text tasks into agent intents."""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from ..ai.llm_router import llm_router
from ..context import PlatformContext

INTENT_AGENTS: dict[str, list[str]] = {
    "deployment": ["deploy_agent"],
    "investigation": ["incident_agent", "alert_noise_agent"],
    "security": ["security_agent", "code_review_agent"],
    "infrastructure": ["infra_agent"],
    "cost": ["cost_agent"],
    "testing": ["tester_agent", "pipeline_monitor_agent"],
    "catalog": ["catalog_health_agent", "documentation_agent"],
    "onboarding": ["onboarding_agent"],
    "scorecard": ["scorecard_agent"],
    "healing": ["auto_heal_agent"],
    "runbook": ["runbook_agent"],
    "drift": ["dependency_drift_agent"],
}

KEYWORD_INTENT: list[tuple[str, str]] = [
    (r"\bdeploy\b", "deployment"),
    (r"\bproduction\b.*\bdown\b|\bwhy is prod\b|\bincident\b", "investigation"),
    (r"\bsecurity\b|\bscan\b|\bcve\b", "security"),
    (r"\binfra\b|\bterraform\b|\bscale\b.*\bcluster\b|\bkubernetes\b", "infrastructure"),
    (r"\btest\b|\bci\b|\bpipeline\b", "testing"),
    (r"\bcatalog\b|\bentity\b", "catalog"),
    (r"\bonboard\b", "onboarding"),
    (r"\bscorecard\b", "scorecard"),
    (r"\bheal\b|\bauto.?heal\b", "healing"),
    (r"\brunbook\b", "runbook"),
    (r"\bdrift\b|\bdependency\b", "drift"),
    (r"\bcost\b|\bbilling\b|\baws\b.*\bmonth\b", "cost"),
]


class ClassifiedIntent(BaseModel):
    intent: str
    confidence: float = 0.0
    suggested_agents: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    environment_hint: Optional[str] = None
    tool_hints: list[str] = Field(default_factory=list)


class IntentClassifier:
    async def classify(self, task: str, context: PlatformContext) -> ClassifiedIntent:
        task_lower = (task or "").lower()
        env_hint = None
        if "production" in task_lower or " prod " in f" {task_lower} ":
            env_hint = "production"
        elif "staging" in task_lower:
            env_hint = "staging"
        elif "dev" in task_lower:
            env_hint = "development"

        tool_hints: list[str] = []
        for tool in ("aws", "github", "kubernetes", "pagerduty", "jira", "terraform"):
            if tool in task_lower:
                tool_hints.append(tool)

        llm_intent = await self._classify_llm(task, context)
        if llm_intent and llm_intent.confidence >= 0.6:
            if env_hint:
                llm_intent.environment_hint = env_hint
            llm_intent.tool_hints = list(set(llm_intent.tool_hints + tool_hints))
            return llm_intent

        for pattern, intent in KEYWORD_INTENT:
            if re.search(pattern, task_lower):
                agents = INTENT_AGENTS.get(intent, ["incident_agent"])
                requires = intent in ("deployment", "healing", "runbook") and (
                    env_hint == "production" or context.is_production()
                )
                return ClassifiedIntent(
                    intent=intent,
                    confidence=0.55,
                    suggested_agents=agents,
                    requires_approval=requires,
                    environment_hint=env_hint,
                    tool_hints=tool_hints,
                )

        return ClassifiedIntent(
            intent="investigation",
            confidence=0.4,
            suggested_agents=["incident_agent"],
            requires_approval=context.is_production(),
            environment_hint=env_hint,
            tool_hints=tool_hints,
        )

    async def _classify_llm(self, task: str, context: PlatformContext) -> Optional[ClassifiedIntent]:
        prompt = (
            "Classify this platform engineering task. Return ONLY JSON:\n"
            '{"intent":"deployment|investigation|security|infrastructure|testing|catalog|onboarding|'
            'scorecard|healing|runbook|drift","confidence":0.0-1.0,"suggested_agents":["agent_name"],'
            '"requires_approval":true|false,"environment_hint":"production|staging|dev|null",'
            '"tool_hints":["aws"]}\n'
            f"Task: {task}\nEnvironment: {context.environment}"
        )
        try:
            raw = await llm_router.chat(
                [{"role": "user", "content": prompt}],
                system_prompt="You are an intent classifier for a DevOps platform.",
            )
            text = raw.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            data = json.loads(text)
            intent = str(data.get("intent") or "investigation")
            agents = data.get("suggested_agents") or INTENT_AGENTS.get(intent, ["incident_agent"])
            return ClassifiedIntent(
                intent=intent,
                confidence=float(data.get("confidence") or 0.7),
                suggested_agents=[str(a) for a in agents],
                requires_approval=bool(data.get("requires_approval")),
                environment_hint=data.get("environment_hint"),
                tool_hints=[str(t) for t in (data.get("tool_hints") or [])],
            )
        except Exception:
            return None


intent_classifier = IntentClassifier()
