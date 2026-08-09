"""Security scanning agent — findings plus HITL AWS remediations with blast radius."""

from __future__ import annotations

import json
import re

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


def _classify_finding(f: dict) -> str | None:
    """Map a finding to a remediable type."""
    if f.get("remediation_type"):
        return str(f["remediation_type"])
    blob = " ".join(
        str(f.get(k) or "")
        for k in ("title", "Title", "description", "type", "resource", "Resource")
    ).lower()
    if f.get("group_id") or "security group" in blob or "0.0.0.0/0" in blob:
        return "overly_permissive_sg"
    if f.get("bucket") or "s3" in blob and "public" in blob:
        return "public_s3"
    if f.get("access_key_id") or ("access key" in blob and ("stale" in blob or "unused" in blob)):
        return "stale_iam_key"
    if f.get("volume_id") or ("ebs" in blob and "encrypt" in blob):
        return "unencrypted_ebs"
    return None


class SecurityAgent(BaseAgent):
    name = "security_agent"
    description = "Security scans: Snyk, SonarQube, Wiz, Checkov, GuardDuty."
    requires_approval_envs = []
    primary_tools = ["Snyk", "SonarQube", "Wiz", "Checkov", "GuardDuty"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
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

        propose = bool(params.get("propose", True))
        remediate = params.get("remediate", True)

        # Prefer direct AWS remediation when a remediable finding is present
        if propose and remediate:
            rem = await self._try_remediation_proposal(
                findings, params, context, db, details, evidence
            )
            if rem is not None:
                return rem

        if propose and (critical or high or findings):
            jira = await self._ground_jira(context, db)
            if jira is None:
                return self._no_data_result(
                    context,
                    "Jira not connected — cannot propose security issues. "
                    "Add Jira in Settings → Tool Registry.",
                    missing_tools=["Jira"],
                    details=details,
                )

            sev_map = {
                "CRITICAL": "Highest",
                "HIGH": "High",
                "MEDIUM": "Medium",
                "LOW": "Low",
            }
            target = (critical or high or findings)[:1]
            f0 = target[0]
            sev = str(f0.get("severity") or f0.get("Severity") or "MEDIUM").upper()
            priority = sev_map.get(sev, "Medium")
            title = str(f0.get("title") or f0.get("Title") or "Security finding")[:180]
            arn = f0.get("arn") or f0.get("Id") or f0.get("id") or ""
            remediation = f0.get("remediation") or f0.get("description") or ""
            project_key = params.get("project_key") or "SEC"
            description = (
                f"Severity: {sev}\nFinding ARN/Id: {arn}\n\n"
                f"Remediation guidance:\n{remediation}"
            )
            return self._propose_artifact_result(
                context,
                connector="jira",
                method="create_issue",
                params={
                    "project_key": project_key,
                    "summary": f"[{sev}] {title}",
                    "description": description,
                    "issue_type": "Bug",
                    "priority": priority,
                    "labels": ["security", "guardduty"],
                },
                preview={
                    "type": "jira_issue",
                    "project_key": project_key,
                    "summary": f"[{sev}] {title}",
                    "priority": priority,
                    "description": description[:4000],
                    "severity_mapped_from": sev,
                },
                grounding="live",
                summary=f"Propose Jira issue for {sev} finding: {title}",
                details={**details, "proposed_priority": priority},
                evidence=evidence,
            )

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

    async def _try_remediation_proposal(
        self,
        findings: list,
        params: dict,
        context: PlatformContext,
        db: Session,
        details: dict,
        evidence: list,
    ) -> AgentResult | None:
        aws = await self._ground_aws(context, db)
        if aws is None:
            return None

        # Prefer explicit remediation payload
        target = None
        rtype = params.get("remediation_type")
        if rtype:
            target = {**params, "remediation_type": rtype}
        else:
            for f in findings:
                rt = _classify_finding(f)
                if rt:
                    target = {**f, "remediation_type": rt}
                    break
        if not target:
            return None

        rtype = target["remediation_type"]
        region = params.get("region") or target.get("region")

        if rtype == "overly_permissive_sg":
            group_id = target.get("group_id") or _extract_sg(target.get("resource") or "")
            if not group_id:
                return None
            usage = target.get("usage") or await aws.describe_security_group_usage(
                group_id, region=region
            )
            revoke = target.get("revoke_ip_permissions") or _open_cidrs_to_revoke(
                usage.get("ingress") or []
            )
            proposed_ingress = target.get("proposed_ingress") or []
            blast = {
                "affected_resources": [group_id, *(usage.get("instances") or [])],
                "risk_note": (
                    "Narrowing this security group may block legitimate traffic to "
                    f"{len(usage.get('instances') or [])} attached instance(s)."
                ),
                "reversible": True,
            }
            return self._propose_artifact_result(
                context,
                connector="aws",
                method="update_security_group_ingress",
                params={
                    "group_id": group_id,
                    "revoke_ip_permissions": revoke,
                    "authorize_ip_permissions": proposed_ingress,
                    "region": region,
                },
                preview={
                    "type": "security_remediation",
                    "remediation_type": rtype,
                    "group_id": group_id,
                    "cidrs_removed": _cidrs_from_perms(revoke),
                    "instances_using_sg": usage.get("instances") or [],
                    "blast_radius": blast,
                },
                grounding="live",
                summary=f"Narrow security group {group_id} ingress",
                details={**details, "blast_radius": blast},
                evidence=evidence,
            )

        if rtype == "public_s3":
            bucket = target.get("bucket") or _extract_bucket(target.get("resource") or "")
            if not bucket:
                return None
            info = target.get("bucket_info") or await aws.get_bucket_public_info(bucket)
            blast = {
                "affected_resources": [bucket],
                "risk_note": (
                    "Enabling the public access block will deny anonymous reads/writes; "
                    "public website hosting or public object URLs will break."
                ),
                "reversible": True,
            }
            return self._propose_artifact_result(
                context,
                connector="aws",
                method="put_public_access_block",
                params={"bucket": bucket},
                preview={
                    "type": "security_remediation",
                    "remediation_type": rtype,
                    "bucket": bucket,
                    "serves_public_objects": info.get("serves_public_objects"),
                    "object_count": info.get("object_count"),
                    "blast_radius": blast,
                },
                grounding="live",
                summary=f"Block public access on S3 bucket {bucket}",
                details={**details, "blast_radius": blast},
                evidence=evidence,
            )

        if rtype == "stale_iam_key":
            key_id = target.get("access_key_id")
            if not key_id:
                return None
            info = target.get("key_info") or await aws.get_access_key_info(key_id)
            user_name = info.get("principal") or target.get("user_name") or ""
            blast = {
                "affected_resources": [key_id, user_name],
                "risk_note": (
                    f"Disabling access key {key_id} owned by {user_name} will break any "
                    "automation still using this key."
                ),
                "reversible": True,
            }
            return self._propose_artifact_result(
                context,
                connector="aws",
                method="update_access_key_status",
                params={
                    "access_key_id": key_id,
                    "user_name": user_name,
                    "status": "Inactive",
                },
                preview={
                    "type": "security_remediation",
                    "remediation_type": rtype,
                    "access_key_id": key_id,
                    "principal": user_name,
                    "key_age_days": info.get("age_days"),
                    "last_used": info.get("last_used"),
                    "blast_radius": blast,
                },
                grounding="live",
                summary=f"Disable stale IAM access key {key_id}",
                details={**details, "blast_radius": blast},
                evidence=evidence,
            )

        if rtype == "unencrypted_ebs":
            volume_id = target.get("volume_id") or _extract_vol(target.get("resource") or "")
            if not volume_id:
                return None
            info = target.get("volume_info") or await aws.get_volume_info(volume_id, region=region)
            attached = [a.get("instance_id") for a in (info.get("attachments") or []) if a.get("instance_id")]
            blast = {
                "affected_resources": [volume_id, *attached],
                "risk_note": (
                    "Encrypting this EBS volume requires a snapshot and volume replacement, "
                    "which causes downtime for the attached instance."
                ),
                "reversible": False,
            }
            return self._propose_artifact_result(
                context,
                connector="aws",
                method="enable_ebs_encryption",
                params={"volume_id": volume_id, "region": region},
                preview={
                    "type": "security_remediation",
                    "remediation_type": rtype,
                    "volume_id": volume_id,
                    "attachments": info.get("attachments") or [],
                    "blast_radius": blast,
                },
                grounding="live",
                summary=f"Encrypt EBS volume {volume_id} (snapshot + replace)",
                details={**details, "blast_radius": blast},
                evidence=evidence,
            )

        return None


def _extract_sg(resource: str) -> str | None:
    m = re.search(r"(sg-[0-9a-f]+)", resource or "", re.I)
    return m.group(1) if m else None


def _extract_bucket(resource: str) -> str | None:
    m = re.search(r"arn:aws:s3:::([^/\s]+)", resource or "")
    if m:
        return m.group(1)
    if resource and "/" not in resource and " " not in resource:
        return resource
    return None


def _extract_vol(resource: str) -> str | None:
    m = re.search(r"(vol-[0-9a-f]+)", resource or "", re.I)
    return m.group(1) if m else None


def _cidrs_from_perms(perms: list) -> list[str]:
    out: list[str] = []
    for p in perms or []:
        for r in p.get("IpRanges") or []:
            if r.get("CidrIp"):
                out.append(r["CidrIp"])
    return out


def _open_cidrs_to_revoke(ingress: list) -> list[dict]:
    """Build revoke set for 0.0.0.0/0 and ::/0 rules."""
    revoke = []
    for p in ingress or []:
        ranges = [
            r for r in (p.get("IpRanges") or []) if r.get("CidrIp") in {"0.0.0.0/0"}
        ]
        v6 = [
            r for r in (p.get("Ipv6Ranges") or []) if r.get("CidrIpv6") in {"::/0"}
        ]
        if ranges or v6:
            entry = {
                "IpProtocol": p.get("IpProtocol", "-1"),
                "FromPort": p.get("FromPort"),
                "ToPort": p.get("ToPort"),
            }
            if ranges:
                entry["IpRanges"] = ranges
            if v6:
                entry["Ipv6Ranges"] = v6
            # Drop None ports for "all traffic"
            if entry.get("FromPort") is None:
                entry.pop("FromPort", None)
                entry.pop("ToPort", None)
            revoke.append(entry)
    return revoke


security_agent = SecurityAgent()
