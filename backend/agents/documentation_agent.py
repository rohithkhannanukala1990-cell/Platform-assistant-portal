from .base import BaseAgent


class DocumentationAgent(BaseAgent):
    name = "documentation_agent"
    description = "Generates and updates service documentation from catalog entities."
    requires_approval_envs = []
    primary_tools = ["Confluence", "GitHub", "Catalog DB"]
    read_only = True


documentation_agent = DocumentationAgent()
