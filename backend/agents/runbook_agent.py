from .base import BaseAgent


class RunbookAgent(BaseAgent):
    name = "runbook_agent"
    description = "Executes and drafts operational runbooks."
    requires_approval_envs = ["production"]
    primary_tools = ["Confluence", "Kubernetes", "Ansible"]


runbook_agent = RunbookAgent()
