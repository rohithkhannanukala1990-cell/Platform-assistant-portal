from .base import BaseAgent


class ScorecardAgent(BaseAgent):
    name = "scorecard_agent"
    description = "Scorecard evaluation and remediation tracking."
    requires_approval_envs = ["production"]
    primary_tools = ["Scorecards DB", "Jira"]


scorecard_agent = ScorecardAgent()
