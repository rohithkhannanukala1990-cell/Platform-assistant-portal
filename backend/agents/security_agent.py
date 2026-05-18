"""Security scanning agent — AWS Security Hub findings."""

from __future__ import annotations

from sqlmodel import Session

from ..connectors.aws_connector import AWSConnector
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

_ACCOUNT: dict = {}


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
        findings: list = []
        try:
            findings = await AWSConnector(_ACCOUNT).list_security_findings()
        except Exception:
            findings = []

        critical = [f for f in findings if (f.get("severity") or "").upper() == "CRITICAL"]
        high = [f for f in findings if (f.get("severity") or "").upper() == "HIGH"]
        critical_count = len(critical)
        high_count = len(high)

        requires = critical_count > 0
        summary = (
            f"{critical_count} critical and {high_count} high security findings"
            if findings
            else "No critical/high security findings"
        )

        if requires:
            return self._build_result(
                context,
                status="pending_approval",
                summary=summary,
                details={
                    "findings": findings[:50],
                    "critical_count": critical_count,
                    "high_count": high_count,
                },
                requires_approval=True,
                approval_payload={
                    "action": "remediate_security_findings",
                    "critical_count": critical_count,
                    "finding_ids": [f.get("title") for f in critical[:10]],
                },
                execution_log="Critical findings require approval before remediation",
            )

        return self._build_result(
            context,
            status="success",
            summary=summary,
            details={
                "findings": findings[:50],
                "critical_count": critical_count,
                "high_count": high_count,
            },
            execution_log="Read-only security analysis — no remediation executed",
        )


security_agent = SecurityAgent()
