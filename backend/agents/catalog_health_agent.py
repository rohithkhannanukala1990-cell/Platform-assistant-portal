from .base import BaseAgent


class CatalogHealthAgent(BaseAgent):
    name = "catalog_health_agent"
    description = "Catalog entity health and metadata quality checks."
    requires_approval_envs = []
    primary_tools = ["Catalog DB"]
    read_only = True


catalog_health_agent = CatalogHealthAgent()
