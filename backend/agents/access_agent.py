"""Access agent — request lifecycle, policy assessment, provisioning, revocation."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from ..context import PlatformContext
from ..db.models.access import AccessRequestRecord, ResourceOwner
from .base import AgentResult, BaseAgent


# resource_type → connector metadata for peer/broader-access lookups.
_RESOURCE_TYPES = {
    "github_team",
    "okta_group",
    "k8s_role",
    "aws_iam_role",
    "jira_project",
}


def parse_request_text(
    task: str, params: dict[str, Any]
) -> tuple[str, str, list[dict[str, Any]]]:
    """Return (resource_type, resource_id, candidates)."""
    text = str(params.get("task") or params.get("message") or task or "")
    rtype = str(params.get("resource_type") or "").strip().lower()
    rid = str(params.get("resource_id") or "").strip()

    candidates: list[dict[str, Any]] = []
    low = text.lower()
    if not rtype:
        if "okta" in low or "group" in low:
            rtype = "okta_group"
        elif "github" in low or "repo" in low or "team" in low:
            rtype = "github_team"
        elif "iam" in low or "aws" in low or "role" in low:
            rtype = "aws_iam_role"
        elif "kube" in low or "k8s" in low or "cluster" in low:
            rtype = "k8s_role"
        elif "jira" in low or "project" in low:
            rtype = "jira_project"
    if not rid:
        # heuristics — pull a slug-like token after a keyword
        for pat in [
            r"access to (?:the )?([\w./\-]+)",
            r"add .* to ([\w./\-]+)",
            r"grant .* (?:to|on) ([\w./\-]+)",
        ]:
            m = re.search(pat, text, re.I)
            if m:
                rid = m.group(1).strip()
                break

    if rtype and rid:
        candidates.append({"resource_type": rtype, "resource_id": rid})
    return rtype, rid, candidates


def check_policy(
    session: Session,
    *,
    tenant_id: str,
    subject_username: str,
    resource_type: str,
    resource_id: str,
    role_level: str | None = None,
) -> dict[str, Any]:
    """Advisory policy check — informs the approver, does not block."""
    findings: list[str] = []
    recommendation = "review"

    # Already-provisioned equivalent access?
    same = list(
        session.exec(
            select(AccessRequestRecord).where(
                AccessRequestRecord.tenant_id == tenant_id,
                AccessRequestRecord.subject_username == subject_username,
                AccessRequestRecord.resource_type == resource_type,
                AccessRequestRecord.status == "provisioned",
            )
        ).all()
    )
    if any(r.resource_id == resource_id for r in same):
        findings.append("Subject already has an active grant to this exact resource")
        recommendation = "reject_duplicate"
    if any(r.resource_id != resource_id for r in same):
        findings.append(
            f"Subject already has {len(same)} active {resource_type} grant(s); "
            "confirm this is not broader/overlapping"
        )
        recommendation = "review_broad_access" if recommendation == "review" else recommendation

    # Peer baseline — how many peers on any team hold this exact resource?
    peers = list(
        session.exec(
            select(AccessRequestRecord).where(
                AccessRequestRecord.tenant_id == tenant_id,
                AccessRequestRecord.resource_type == resource_type,
                AccessRequestRecord.resource_id == resource_id,
                AccessRequestRecord.status == "provisioned",
            )
        ).all()
    )
    peer_count = sum(1 for p in peers if p.subject_username != subject_username)
    if peer_count == 0:
        findings.append(
            "No peers currently hold this resource — grant would be net-new access"
        )
        if recommendation == "review":
            recommendation = "review_no_peers"

    return {
        "recommendation": recommendation,
        "reasoning": findings,
        "peer_count": peer_count,
        "existing_grants": [
            {"resource_id": r.resource_id, "status": r.status}
            for r in same
        ],
    }


class AccessAgent(BaseAgent):
    name = "access_agent"
    description = "Route access requests to resource owners, provision on approval."
    primary_tools = ["Okta", "GitHub", "AWS", "Jira", "Kubernetes"]
    read_only = False

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        action = (params.get("action") or "propose_provisioning").lower()

        if action in {"parse", "parse_request"}:
            return self._parse(params, context)
        if action in {"check_policy", "assess"}:
            return self._assess(params, context, db)
        if action in {"revoke"}:
            return await self._revoke(params, context)
        return await self._propose(params, context, db)

    def _parse(self, params: dict, context: PlatformContext) -> AgentResult:
        rtype, rid, candidates = parse_request_text(str(params.get("task") or ""), params)
        if not rtype or not rid:
            return self._result(
                context,
                status="success",
                summary="Could not resolve resource — please provide resource_type and resource_id",
                details={
                    "candidates": candidates,
                    "needs_clarification": True,
                    "hint": (
                        "Provide resource_type (github_team|okta_group|k8s_role|"
                        "aws_iam_role|jira_project) and resource_id."
                    ),
                },
                grounding="none",
                confidence=0.2,
            )
        return self._result(
            context,
            status="success",
            summary=f"Parsed access request → {rtype}:{rid}",
            details={"resource_type": rtype, "resource_id": rid, "candidates": candidates},
            grounding="partial",
            confidence=0.6,
        )

    def _assess(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        subject = str(params.get("subject_username") or context.user_id or "")
        rtype = str(params.get("resource_type") or "")
        rid = str(params.get("resource_id") or "")
        assessment = check_policy(
            db,
            tenant_id=context.tenant_id or "default",
            subject_username=subject,
            resource_type=rtype,
            resource_id=rid,
            role_level=params.get("role_level"),
        )
        return self._result(
            context,
            status="success",
            summary=f"Policy: {assessment.get('recommendation')} for {rtype}:{rid}",
            details=assessment,
            grounding="live",
            confidence=0.75,
        )

    async def _propose(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
        from ..services.access_service import (
            RESOURCE_TYPE_MAP,
            create_access_request,
            route_owner,
        )

        rtype = str(params.get("resource_type") or "").strip()
        rid = str(params.get("resource_id") or "").strip()
        if not rtype or not rid:
            rtype2, rid2, _ = parse_request_text(str(params.get("task") or ""), params)
            rtype = rtype or rtype2
            rid = rid or rid2
        if not rtype or not rid:
            return self._result(
                context,
                status="pending_approval",
                summary="Access request needs clarification — resource_type/resource_id missing",
                details={"needs_clarification": True},
                requires_approval=False,
                grounding="none",
                confidence=0.2,
            )
        if rtype not in _RESOURCE_TYPES:
            return self._result(
                context,
                status="failed",
                summary=f"Unsupported resource_type: {rtype}",
                details={"supported": sorted(_RESOURCE_TYPES)},
                grounding="none",
                confidence=0.2,
            )
        # Missing connector → _no_data_result for okta_group / other identity systems
        if rtype == "okta_group":
            okta = await self._ground_okta(context, db)
            if okta is None:
                return self._no_data_result(
                    context,
                    "Okta not connected — connect Okta in Tool Registry to route this grant.",
                    missing_tools=["Okta"],
                )

        subject = str(params.get("subject_username") or context.user_id or "")
        requester = str(context.user_id or subject)
        justification = str(params.get("justification") or "")
        duration_hours = params.get("duration_hours")
        try:
            duration_hours = int(duration_hours) if duration_hours else None
        except (TypeError, ValueError):
            duration_hours = None

        assessment = check_policy(
            db,
            tenant_id=context.tenant_id or "default",
            subject_username=subject,
            resource_type=rtype,
            resource_id=rid,
        )
        row = create_access_request(
            tenant_id=context.tenant_id or "default",
            workspace_id=context.workspace_id or None,
            requester=requester,
            subject=subject,
            resource_type=rtype,
            resource_id=rid,
            resource_name=str(params.get("resource_name") or rid),
            justification=justification,
            duration_hours=duration_hours,
            policy_assessment=assessment,
        )
        owner, missing = route_owner(context.tenant_id or "default", rtype, rid)
        mapping = RESOURCE_TYPE_MAP.get(rtype) or {}

        summary = (
            f"Access request → {rtype}:{rid} for {subject} "
            f"(owner={owner}{' [NO OWNER REGISTERED, routed to admin]' if missing else ''})"
        )
        return self._result(
            context,
            status="pending_approval",
            summary=summary,
            details={
                "access_request_id": row.id,
                "resource_type": rtype,
                "resource_id": rid,
                "subject_username": subject,
                "requester_username": requester,
                "owner_username": owner,
                "owner_missing": missing,
                "duration_hours": duration_hours,
                "justification": justification,
                "policy_assessment": assessment,
                "connector": mapping.get("connector"),
                "connector_method": mapping.get("provision"),
            },
            requires_approval=True,
            approval_payload={
                "access_request_id": row.id,
                "resource_type": rtype,
                "resource_id": rid,
                "subject_username": subject,
                "owner_username": owner,
                "owner_missing": missing,
            },
            grounding="live" if not missing else "partial",
            confidence=0.7,
            evidence=[
                self._evidence(
                    type="access_request",
                    title=f"AccessRequest {row.id}",
                    source="access_agent",
                    snippet=json.dumps(
                        {
                            "id": row.id,
                            "resource_type": rtype,
                            "resource_id": rid,
                            "owner": owner,
                            "owner_missing": missing,
                            "policy_assessment": assessment,
                        },
                        default=str,
                    ),
                )
            ],
            recommended_actions=[
                {
                    "title": f"Approve {rtype} grant for {subject}",
                    "risk": "medium" if missing else "low",
                    "requires_approval": True,
                }
            ],
        )

    async def _revoke(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..auth import User
        from ..db.core import engine
        from ..services.access_service import revoke_access_request

        request_id = str(params.get("access_request_id") or "").strip()
        if not request_id:
            return self._result(
                context,
                status="failed",
                summary="revoke requires access_request_id",
                grounding="none",
                confidence=0.0,
            )
        # Resolve caller user (best-effort) — falls back to system user identity
        user = None
        try:
            with Session(engine) as session:
                user = session.exec(
                    select(User).where(User.username == (context.user_id or ""))
                ).first()
        except Exception:
            user = None
        result = await revoke_access_request(
            request_id=request_id,
            tenant_id=context.tenant_id or "default",
            actor=context.user_id or "system",
            user=user or User(
                username=context.user_id or "system",
                email="",
                hashed_password="",
                role="Admin",
                tenant_id=context.tenant_id or "default",
            ),
            reason=str(params.get("reason") or "manual"),
        )
        return self._result(
            context,
            status="success" if result.get("ok") else "failed",
            summary=f"Revoke {request_id}: ok={result.get('ok')}",
            details=result,
            grounding="live",
            confidence=0.85,
        )


access_agent = AccessAgent()
