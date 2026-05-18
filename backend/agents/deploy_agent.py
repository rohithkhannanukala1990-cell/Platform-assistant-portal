from .base import BaseAgent


class DeployAgent(BaseAgent):
    name = "deploy_agent"
    description = "Builds and applies deployment plans via CI/CD and Kubernetes."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub Actions", "ArgoCD", "Kubernetes", "Helm"]


deploy_agent = DeployAgent()
