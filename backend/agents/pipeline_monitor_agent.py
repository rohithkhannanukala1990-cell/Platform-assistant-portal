from .base import BaseAgent


class PipelineMonitorAgent(BaseAgent):
    name = "pipeline_monitor_agent"
    description = "Monitors CI/CD pipeline status and failures."
    requires_approval_envs = []
    primary_tools = ["Jenkins", "CircleCI", "GitHub Actions", "ArgoCD"]
    read_only = True


pipeline_monitor_agent = PipelineMonitorAgent()
