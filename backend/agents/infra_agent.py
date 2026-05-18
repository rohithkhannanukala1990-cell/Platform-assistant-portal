from .base import BaseAgent


class InfraAgent(BaseAgent):
    name = "infra_agent"
    description = "Terraform/Pulumi infrastructure changes across cloud providers."
    requires_approval_envs = ["production"]
    primary_tools = ["Terraform", "Pulumi", "AWS", "GCP", "Azure"]


infra_agent = InfraAgent()
