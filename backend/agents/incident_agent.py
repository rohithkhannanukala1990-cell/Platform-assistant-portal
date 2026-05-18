from .base import BaseAgent


class IncidentAgent(BaseAgent):
    name = "incident_agent"
    description = "Incident triage, paging, and remediation coordination."
    requires_approval_envs = ["production"]
    primary_tools = ["PagerDuty", "OpsGenie", "Kubernetes"]


incident_agent = IncidentAgent()
