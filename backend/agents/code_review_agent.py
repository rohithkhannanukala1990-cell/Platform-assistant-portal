from .base import BaseAgent


class CodeReviewAgent(BaseAgent):
    name = "code_review_agent"
    description = "PR and repository code review assistance."
    requires_approval_envs = []
    primary_tools = ["GitHub", "GitLab", "SonarQube"]
    read_only = True


code_review_agent = CodeReviewAgent()
