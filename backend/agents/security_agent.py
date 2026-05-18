"""Security scanning agent — read-only analysis."""

from __future__ import annotations

import json

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent

SECURITY_SYSTEM_PROMPT = """
You are SecurityAgent — analyze security events and return ONLY valid JSON:
{"severity":"High","summary":"...","root_cause":"...","details":{"findings":[]},"commands":[],"requires_approval":false}
"""

SECURITY_SOURCES = {
    "falco", "snyk", "dependabot", "trivy", "grype",
    "prisma", "aqua", "sysdig", "checkov", "semgrep",
}


def is_security_source(source: str) -> bool:
    return (
        source.lower() in SECURITY_SOURCES
        or "security" in source.lower()
        or "cve" in source.lower()
    )


class SecurityAgent(BaseAgent):
    name = "security_agent"
    description = "Security scans: Snyk, SonarQube, Wiz, Checkov, GuardDuty."
    requires_approval_envs = []
    primary_tools = ["Snyk", "SonarQube", "Wiz", "Checkov", "GuardDuty"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        scan_target = params.get("scan_target") or params.get("task") or "service"
        scan_type = params.get("scan_type") or "full"
        prompt = (
            f"{SECURITY_SYSTEM_PROMPT}\n"
            f"Scan target: {scan_target}\nScan type: {scan_type}\n"
            f"Environment: {context.environment}"
        )
        raw = await self._call_llm(prompt, context)
        parsed = self._parse_llm_json(raw)
        return self._build_result(
            context,
            status="success",
            summary=str(parsed.get("summary") or "Security scan completed"),
            details={"findings": parsed, "scan_target": scan_target, "scan_type": scan_type},
            execution_log="Read-only security analysis — no commands executed",
        )


security_agent = SecurityAgent()
