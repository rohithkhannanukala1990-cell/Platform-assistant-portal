from .base import BaseAgent


class DependencyDriftAgent(BaseAgent):
    name = "dependency_drift_agent"
    description = "Detects dependency and catalog drift vs repositories."
    requires_approval_envs = []
    primary_tools = ["Catalog DB", "GitHub"]
    read_only = True


dependency_drift_agent = DependencyDriftAgent()
