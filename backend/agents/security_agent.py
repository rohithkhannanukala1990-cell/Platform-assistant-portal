"""Security scanning agent — grounded findings only (never invent clean)."""

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
        params = params if isinstance(params, dict) else {}
        # Prefer explicit findings payload when provided (already grounded).
        injected = params.get("findings")
        if isinstance(injected, list) and injected:
            findings = injected
            source = "params"
        else:
            conn = await self._ground_aws(context, db)
            if conn is None:
                return self._no_data_result(
                    context,
                    "AWS GuardDuty not connected — add AWS credentials in Tool Registry "
                    "under Settings → Tool Registry → AWS.",
                    missing_tools=["GuardDuty", "AWS"],
                )
            try:
                findings = await conn.list_security_findings()
                source = "aws_security_hub"
            except Exception as exc:
                return self._no_data_result(
                    context,
                    f"Security findings source failed: {str(exc)[:200]}",
                    missing_tools=["GuardDuty", "AWS"],
                )

            # Connector swallows errors as [] — without a successful signal treat as no source.
            if not findings and params.get("accept_empty") is not True:
                return self._no_data_result(
                    context,
                    "No security findings source returned data (not reporting clean). "
                    "Connect Security Hub / GuardDuty or pass findings.",
                    missing_tools=["GuardDuty", "AWS"],
                )

        evidence: list[dict] = []
        severity_counts: dict[str, int] = {}
        for f in findings:
            sev = str(f.get("severity") or f.get("Severity") or "UNKNOWN").upper()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            evidence.append(
                self._evidence(
                    type="security_finding",
                    title=str(f.get("title") or f.get("Title") or "finding")[:200],
                    source=source,
                    snippet=json.dumps(
                        {
                            "severity": sev,
                            "resource": f.get("resource") or f.get("Resource"),
                            "description": (f.get("description") or "")[:400],
                        },
                        default=str,
                    )[:1200],
                    severity=sev,
                )
            )

        critical = [f for f in findings if str(f.get("severity") or "").upper() == "CRITICAL"]
        high = [f for f in findings if str(f.get("severity") or "").upper() == "HIGH"]
        critical_count = len(critical)
        high_count = len(high)

        summary = f"{critical_count} critical and {high_count} high security findings"
        details = {
            "findings": findings[:50],
            "critical_count": critical_count,
            "high_count": high_count,
            "severity_counts": severity_counts,
            "source": source,
        }

        if critical_count > 0:
            return self._result(
                context,
                status="success",
                summary=summary,
                details={**details, "commands": []},
                requires_approval=False,
                evidence=evidence,
                grounding="live",
                confidence=0.85,
                recommended_actions=[
                    {
                        "title": "Review and remediate critical findings",
                        "risk": "high",
                        "requires_approval": True,
                        "finding_ids": [f.get("title") for f in critical[:10]],
                    }
                ],
            )

        return self._result(
            context,
            status="success",
            summary=summary,
            details=details,
            evidence=evidence,
            grounding="live",
            confidence=0.85 if findings else 0.7,
            execution_log="Read-only security analysis — no remediation executed",
        )


security_agent = SecurityAgent()
