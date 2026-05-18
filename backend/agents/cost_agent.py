from .base import BaseAgent


class CostAgent(BaseAgent):
    name = "cost_agent"
    description = "Cloud cost breakdown and optimization recommendations."
    requires_approval_envs = []
    primary_tools = ["AWS", "GCP", "Azure"]
    read_only = True


cost_agent = CostAgent()
