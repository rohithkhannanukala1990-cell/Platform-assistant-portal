"""Classify free-text tasks into agent intents."""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from ..agents import AGENT_REGISTRY
from ..ai.llm_router import llm_router
from ..context import PlatformContext

# Full keyword → agent routing (16 specialist agents)
AGENT_KEYWORDS: list[tuple[str, str]] = [
    (r"\bdeploy\b|\brollout\b|\brelease\b", "deploy_agent"),
    (r"\bincident\b|\btriage\b|\boutage\b|\bprod down\b", "incident_agent"),
    (r"\bnoise\b|\balert fatigue\b|\bnoisy alert\b", "alert_noise_agent"),
    (r"\bsecurity\b|\bcve\b|\bvulnerabilit|\bscan\b", "security_agent"),
    (r"\binfra\b|\bterraform\b|\bec2\b|\bcluster\b|\bkubernetes\b|\bk8s\b", "infra_agent"),
    (r"\bcost\b|\bbilling\b|\bspend\b|\baws\b.*\bmonth\b", "cost_agent"),
    (r"\bpull request\b|\bcode review\b|\breview pr\b|\bopen pr\b", "code_review_agent"),
    (r"\brunbook\b", "runbook_agent"),
    (r"\bcatalog\b|\bentity health\b|\bcompleteness\b", "catalog_health_agent"),
    (r"\bpipeline fail\b|\bworkflow fail\b|\bci fail\b|\bactions fail\b", "pipeline_monitor_agent"),
    (r"\bheal\b|\bauto.?heal\b|\brestart pod\b", "auto_heal_agent"),
    (r"\bonboard\b|\bnew service\b|\bgolden path\b", "onboarding_agent"),
    (r"\bdocumentation\b|\breadme\b|\bstaleness\b|\bdocs\b", "documentation_agent"),
    (r"\bscorecard\b", "scorecard_agent"),
    (r"\bdrift\b|\bdependency\b|\boutdated package\b|\bpackage\.json\b", "dependency_drift_agent"),
    (r"\btest\b|\bpytest\b|\bjunit\b|\btest suite\b", "tester_agent"),
]

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
    "multi": [],
    "unknown": [],
}


class ClassifiedIntent(BaseModel):
    intent: str
    confidence: float = 0.0
    suggested_agents: list[str] = Field(default_factory=list)
    requires_approval: bool = False
    environment_hint: Optional[str] = None
    tool_hints: list[str] = Field(default_factory=list)


class IntentClassifier:
    def _env_and_tools(self, task_lower: str) -> tuple[Optional[str], list[str]]:
        env_hint = None
        if "production" in task_lower or " prod " in f" {task_lower} ":
            env_hint = "production"
        elif "staging" in task_lower:
            env_hint = "staging"
        elif "dev" in task_lower or "development" in task_lower:
            env_hint = "development"

        tool_hints: list[str] = []
        for tool in ("aws", "github", "kubernetes", "pagerduty", "jira", "terraform"):
            if tool in task_lower:
                tool_hints.append(tool)
        return env_hint, tool_hints

    def _match_agents(self, text: str) -> list[str]:
        text = (text or "").lower()
        matched: list[str] = []
        for pattern, agent in AGENT_KEYWORDS:
            if re.search(pattern, text) and agent not in matched:
                matched.append(agent)
        return matched

    def _match_multi(self, task: str) -> list[str]:
        """Detect multiple agents when task contains 'and' or comma-separated clauses."""
        agents: list[str] = []
        if re.search(r"\band\b|,", task, re.I):
            segments = re.split(r"\s+and\s+|,\s*", task, flags=re.I)
            for segment in segments:
                for agent in self._match_agents(segment):
                    if agent not in agents:
                        agents.append(agent)
        else:
            agents = self._match_agents(task)
        return agents

    async def classify(self, task: str, context: PlatformContext) -> ClassifiedIntent:
        task_lower = (task or "").lower()
        env_hint, tool_hints = self._env_and_tools(task_lower)

        agents = self._match_multi(task)
        if agents:
            intent = "multi" if len(agents) > 1 else self._intent_for_agent(agents[0])
            requires = any(
                a in ("deploy_agent", "auto_heal_agent", "runbook_agent", "onboarding_agent")
                for a in agents
            ) and (env_hint == "production" or context.is_production())
            return ClassifiedIntent(
                intent=intent,
                confidence=0.75 if len(agents) == 1 else 0.7,
                suggested_agents=agents,
                requires_approval=requires,
                environment_hint=env_hint,
                tool_hints=tool_hints,
            )

        llm_intent = await self._classify_llm(task, context)
        if llm_intent and llm_intent.suggested_agents:
            if env_hint:
                llm_intent.environment_hint = env_hint
            llm_intent.tool_hints = list(set(llm_intent.tool_hints + tool_hints))
            return llm_intent

        return ClassifiedIntent(
            intent="unknown",
            confidence=0.0,
            suggested_agents=[],
            requires_approval=False,
            environment_hint=env_hint,
            tool_hints=tool_hints,
        )

    @staticmethod
    def _intent_for_agent(agent: str) -> str:
        for intent, names in INTENT_AGENTS.items():
            if agent in names:
                return intent
        return "investigation"

    async def _classify_llm(self, task: str, context: PlatformContext) -> Optional[ClassifiedIntent]:
        agent_list = ", ".join(sorted(AGENT_REGISTRY.keys()))
        prompt = (
            "Classify this platform engineering task. Return ONLY JSON:\n"
            '{"intent":"deployment|investigation|security|infrastructure|testing|catalog|'
            'onboarding|scorecard|healing|runbook|drift|cost|multi|unknown",'
            '"confidence":0.0-1.0,"suggested_agents":["agent_name"],'
            '"requires_approval":true|false,"environment_hint":"production|staging|dev|null",'
            '"tool_hints":["aws"]}\n'
            f"Available agents: {agent_list}\n"
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
            intent = str(data.get("intent") or "unknown")
            agents = [str(a) for a in (data.get("suggested_agents") or []) if a in AGENT_REGISTRY]
            if not agents:
                return None
            return ClassifiedIntent(
                intent=intent,
                confidence=float(data.get("confidence") or 0.65),
                suggested_agents=agents,
                requires_approval=bool(data.get("requires_approval")),
                environment_hint=data.get("environment_hint"),
                tool_hints=[str(t) for t in (data.get("tool_hints") or [])],
            )
        except Exception:
            return None


intent_classifier = IntentClassifier()
