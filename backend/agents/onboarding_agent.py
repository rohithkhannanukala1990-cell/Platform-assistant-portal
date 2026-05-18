from .base import BaseAgent


class OnboardingAgent(BaseAgent):
    name = "onboarding_agent"
    description = "Team and service onboarding via golden paths."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub", "Jira", "GoldenPaths DB"]


onboarding_agent = OnboardingAgent()
