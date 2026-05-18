"""Agent registry — 16 specialist agents."""

from .alert_noise_agent import alert_noise_agent
from .auto_heal_agent import auto_heal_agent
from .base import AgentResult, BaseAgent
from .catalog_health_agent import catalog_health_agent
from .code_review_agent import code_review_agent
from .cost_agent import cost_agent
from .dependency_drift_agent import dependency_drift_agent
from .deploy_agent import deploy_agent
from .documentation_agent import documentation_agent
from .incident_agent import incident_agent
from .infra_agent import infra_agent
from .onboarding_agent import onboarding_agent
from .pipeline_monitor_agent import pipeline_monitor_agent
from .runbook_agent import runbook_agent
from .scorecard_agent import scorecard_agent
from .security_agent import security_agent, is_security_source, SECURITY_SYSTEM_PROMPT
from .tester_agent import tester_agent, is_tester_source, TESTER_SYSTEM_PROMPT

AGENT_REGISTRY: dict[str, BaseAgent] = {
    "deploy_agent": deploy_agent,
    "security_agent": security_agent,
    "tester_agent": tester_agent,
    "infra_agent": infra_agent,
    "incident_agent": incident_agent,
    "cost_agent": cost_agent,
    "code_review_agent": code_review_agent,
    "runbook_agent": runbook_agent,
    "catalog_health_agent": catalog_health_agent,
    "pipeline_monitor_agent": pipeline_monitor_agent,
    "auto_heal_agent": auto_heal_agent,
    "onboarding_agent": onboarding_agent,
    "documentation_agent": documentation_agent,
    "scorecard_agent": scorecard_agent,
    "dependency_drift_agent": dependency_drift_agent,
    "alert_noise_agent": alert_noise_agent,
}


class AgentNotFound(KeyError):
    pass


def get_agent(name: str) -> BaseAgent:
    if name not in AGENT_REGISTRY:
        raise AgentNotFound(f"Agent '{name}' not registered")
    return AGENT_REGISTRY[name]


def list_agents() -> list[dict]:
    return [
        {
            "name": agent.name,
            "description": agent.description,
            "requires_approval_envs": agent.requires_approval_envs,
            "primary_tools": agent.primary_tools,
        }
        for agent in AGENT_REGISTRY.values()
    ]
