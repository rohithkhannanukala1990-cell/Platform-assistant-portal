from .base import BaseAgent


class AlertNoiseAgent(BaseAgent):
    name = "alert_noise_agent"
    description = "Alert noise analysis and deduplication recommendations."
    requires_approval_envs = []
    primary_tools = ["PagerDuty", "Datadog", "Grafana", "Prometheus"]
    read_only = True


alert_noise_agent = AlertNoiseAgent()
