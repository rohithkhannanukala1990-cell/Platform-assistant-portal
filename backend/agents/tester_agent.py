"""QA / test failure analysis agent."""

from __future__ import annotations

from sqlmodel import Session

from ..context import PlatformContext
from .base import BaseAgent

TESTER_SYSTEM_PROMPT = """
You are TesterAgent — analyze test failures and return ONLY valid JSON with:
summary, commands (test retry commands), details, requires_approval (true for production).
"""

TESTER_SOURCES = {
    "cypress", "playwright", "jest", "pytest", "testng",
    "codecov", "sonarqube", "sonar", "testrail", "coverage",
}


def is_tester_source(source: str) -> bool:
    return source.lower() in TESTER_SOURCES or "test" in source.lower()


class TesterAgent(BaseAgent):
    name = "tester_agent"
    description = "Runs and analyzes test suites via CI pipelines."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub Actions", "CircleCI", "Jenkins"]


tester_agent = TesterAgent()
