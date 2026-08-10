"""Onboarding agent — real access provisioning via workflow engine + team template."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from ..context import PlatformContext
from ..db.models.access import (
    AccessRequestRecord,
    ResourceOwner,
    TeamAccessTemplate,
)
from ..db.models.workflows import WorkflowDefinition, WorkflowRun
from .base import AgentResult, BaseAgent


def _match(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


def _parse_onboarding_params(task: str, params: dict) -> dict[str, Any]:
    text = f"{params.get('task') or params.get('message') or task or ''}"
    return {
        "subject_username": params.get("subject_username")
        or params.get("subject")
        or params.get("username")
        or _match(text, r"onboard\s+([\w.\-@]+)")
        or "",
        "email": params.get("email") or _match(text, r"email[=:\s]+['\"]?([\w.@\-]+)"),
        "team": params.get("team") or _match(text, r"team[=:\s]+['\"]?([\w-]+)") or "platform",
        "role_level": params.get("role_level") or params.get("role") or "junior",
        "start_date": params.get("start_date"),
    }


def _get_team_template(
    session: Session, tenant_id: str, team: str, role_level: str
) -> list[dict[str, Any]] | None:
    row = session.exec(
        select(TeamAccessTemplate).where(
            TeamAccessTemplate.tenant_id == tenant_id,
            TeamAccessTemplate.team_name == team,
            TeamAccessTemplate.role_level == role_level,
        )
    ).first()
    if row is None:
        # Fall back to junior if role_level not found
        row = session.exec(
            select(TeamAccessTemplate).where(
                TeamAccessTemplate.tenant_id == tenant_id,
                TeamAccessTemplate.team_name == team,
            )
        ).first()
    if row is None:
        return None
    try:
        rows = json.loads(row.resources_json or "[]")
    except Exception:
        rows = []
    return rows if isinstance(rows, list) else []


def _resolve_owner(
    session: Session, tenant_id: str, resource_type: str, resource_id: str
) -> tuple[str, bool]:
    row = session.exec(
        select(ResourceOwner).where(
            ResourceOwner.tenant_id == tenant_id,
            ResourceOwner.resource_type == resource_type,
            ResourceOwner.resource_id == resource_id,
        )
    ).first()
    if row and row.owner_username:
        return row.owner_username, False
    return "admin", True


def _build_onboarding_steps(
    *,
    subject: str,
    resources: list[dict[str, Any]],
    owner_lookup,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for idx, res in enumerate(resources or []):
        if not isinstance(res, dict):
            continue
        rtype = str(res.get("resource_type") or "").strip()
        rid = str(res.get("resource_id") or "").strip()
        if not rtype or not rid:
            continue
        owner, _missing = owner_lookup(rtype, rid)
        gate_id = f"gate_{idx}"
        provision_id = f"provision_{idx}"
        steps.append(
            {
                "id": gate_id,
                "type": "hitl",
                "prompt": (
                    f"Approve {rtype}:{rid} for {subject}? owner={owner}"
                ),
                "depends_on": [],
                "resource_type": rtype,
                "resource_id": rid,
                "owner_username": owner,
                "subject_username": subject,
            }
        )
        steps.append(
            {
                "id": provision_id,
                "type": "agent",
                "agent": "access_agent",
                "depends_on": [gate_id],
                "input": {
                    "action": "propose_provisioning",
                    "resource_type": rtype,
                    "resource_id": rid,
                    "subject_username": subject,
                    "justification": res.get("justification") or f"Onboarding {subject}",
                },
                "resource_type": rtype,
                "resource_id": rid,
                "owner_username": owner,
            }
        )
    return steps


def _build_offboarding_steps(
    *,
    subject: str,
    active_grants: list[AccessRequestRecord],
    okta_user_id: str | None,
) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    prior_ids: list[str] = []
    for idx, grant in enumerate(active_grants):
        gate_id = f"revoke_gate_{idx}"
        revoke_id = f"revoke_{idx}"
        steps.append(
            {
                "id": gate_id,
                "type": "hitl",
                "prompt": (
                    f"Revoke {grant.resource_type}:{grant.resource_id} "
                    f"from {subject}?"
                ),
                "depends_on": [],
                "access_request_id": grant.id,
                "resource_type": grant.resource_type,
                "resource_id": grant.resource_id,
            }
        )
        steps.append(
            {
                "id": revoke_id,
                "type": "agent",
                "agent": "access_agent",
                "depends_on": [gate_id],
                "input": {
                    "action": "revoke",
                    "access_request_id": grant.id,
                    "reason": "offboarding",
                },
                "access_request_id": grant.id,
            }
        )
        prior_ids.append(revoke_id)

    # Final Okta deactivation with its own separate approval, depending on all
    # revokes so it always runs last.
    steps.append(
        {
            "id": "okta_deactivate_gate",
            "type": "hitl",
            "prompt": (
                f"Deactivate Okta user {subject}? This is irreversible and is a "
                "separate approval from access revocations."
            ),
            "depends_on": prior_ids,
            "irreversible": True,
            "final": True,
            "requires_separate_approval": True,
        }
    )
    steps.append(
        {
            "id": "okta_deactivate",
            "type": "connector",
            "connector": "okta",
            "method": "deactivate_user",
            "depends_on": ["okta_deactivate_gate"],
            "input": {"user_id": okta_user_id or subject},
            "final": True,
            "requires_approval": True,
        }
    )
    return steps


class OnboardingAgent(BaseAgent):
    name = "onboarding_agent"
    description = "Onboard new hires by chaining access requests to resource owners."
    primary_tools = ["Okta", "GitHub", "Jira"]
    read_only = False

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        action = (params.get("action") or "onboard").lower()
        if action in {"offboard"}:
            return await self._offboard(params, context, db)
        if action in {"check_onboarding_status", "status"}:
            return self._check_status(params, context, db)
        return await self._onboard(params, context, db)

    async def _onboard(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
        parsed = _parse_onboarding_params(str(params.get("task") or ""), params)
        subject = parsed["subject_username"] or params.get("subject_username") or ""
        team = parsed["team"]
        role_level = parsed["role_level"]

        if not subject:
            return self._result(
                context,
                status="failed",
                summary="Onboarding requires subject_username",
                grounding="none",
                confidence=0.0,
            )

        resources = _get_team_template(
            db, context.tenant_id or "default", team, role_level
        )
        if resources is None:
            return self._result(
                context,
                status="failed",
                summary=(
                    f"No team access template for team={team} role_level={role_level}. "
                    "Register a TeamAccessTemplate first."
                ),
                details={"team": team, "role_level": role_level},
                grounding="none",
                confidence=0.2,
            )

        def _own(rtype: str, rid: str) -> tuple[str, bool]:
            return _resolve_owner(db, context.tenant_id or "default", rtype, rid)

        steps = _build_onboarding_steps(
            subject=subject,
            resources=resources,
            owner_lookup=_own,
        )

        # Persist workflow definition + start a run (approvals happen per-step).
        wf = WorkflowDefinition(
            id=str(uuid.uuid4()),
            tenant_id=context.tenant_id or "default",
            workspace_id=context.workspace_id or None,
            name=f"onboard:{subject}",
            description=f"Onboarding workflow for {subject} on team {team}",
            steps_json=json.dumps(steps, default=str),
            trigger_type="manual",
            trigger_config_json="{}",
            risk="medium",
            created_by=context.user_id or "system",
        )
        db.add(wf)
        db.commit()
        db.refresh(wf)

        run = WorkflowRun(
            id=str(uuid.uuid4()),
            tenant_id=context.tenant_id or "default",
            workflow_id=wf.id,
            status="pending_approval",
            context_json=json.dumps(
                {
                    "trigger": {
                        "subject": subject,
                        "team": team,
                        "role_level": role_level,
                    },
                    "steps": {},
                },
                default=str,
            ),
            steps_state_json="{}",
            triggered_by=context.user_id or "system",
            grounding="live",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        return self._result(
            context,
            status="pending_approval",
            summary=(
                f"Onboarding workflow for {subject} ({team}/{role_level}) with "
                f"{len(resources)} access request step(s)"
            ),
            details={
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "subject_username": subject,
                "team": team,
                "role_level": role_level,
                "resources": resources,
                "steps": steps,
            },
            requires_approval=True,
            approval_payload={
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "steps": [
                    {"id": s.get("id"), "owner": s.get("owner_username")}
                    for s in steps
                    if s.get("type") == "hitl"
                ],
            },
            grounding="live",
            confidence=0.8,
        )

    async def _offboard(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
        subject = str(
            params.get("subject_username")
            or params.get("username")
            or ""
        ).strip()
        if not subject:
            return self._result(
                context,
                status="failed",
                summary="Offboarding requires subject_username",
                grounding="none",
                confidence=0.0,
            )
        active_grants = list(
            db.exec(
                select(AccessRequestRecord).where(
                    AccessRequestRecord.tenant_id == (context.tenant_id or "default"),
                    AccessRequestRecord.subject_username == subject,
                    AccessRequestRecord.status == "provisioned",
                )
            ).all()
        )
        okta_user_id = params.get("okta_user_id") or subject
        steps = _build_offboarding_steps(
            subject=subject,
            active_grants=active_grants,
            okta_user_id=str(okta_user_id),
        )

        wf = WorkflowDefinition(
            id=str(uuid.uuid4()),
            tenant_id=context.tenant_id or "default",
            workspace_id=context.workspace_id or None,
            name=f"offboard:{subject}",
            description=f"Offboarding workflow for {subject}",
            steps_json=json.dumps(steps, default=str),
            trigger_type="manual",
            trigger_config_json="{}",
            risk="high",
            created_by=context.user_id or "system",
        )
        db.add(wf)
        db.commit()
        db.refresh(wf)

        run = WorkflowRun(
            id=str(uuid.uuid4()),
            tenant_id=context.tenant_id or "default",
            workflow_id=wf.id,
            status="pending_approval",
            context_json=json.dumps(
                {"trigger": {"subject": subject}, "steps": {}}, default=str
            ),
            steps_state_json="{}",
            triggered_by=context.user_id or "system",
            grounding="live",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        return self._result(
            context,
            status="pending_approval",
            summary=(
                f"Offboarding workflow for {subject}: "
                f"{len(active_grants)} access revocation(s) then Okta deactivation"
            ),
            details={
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "subject_username": subject,
                "revocations": [
                    {
                        "access_request_id": g.id,
                        "resource_type": g.resource_type,
                        "resource_id": g.resource_id,
                    }
                    for g in active_grants
                ],
                "steps": steps,
                "irreversible_final_step": "okta_deactivate",
            },
            requires_approval=True,
            approval_payload={
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "final_step": "okta_deactivate",
                "separate_approval_required": True,
            },
            grounding="live",
            confidence=0.85,
        )

    def _check_status(
        self, params: dict, context: PlatformContext, db: Session
    ) -> AgentResult:
        workflow_id = str(params.get("workflow_id") or "").strip()
        subject = str(params.get("subject_username") or "").strip()
        run = None
        wf = None
        if workflow_id:
            wf = db.get(WorkflowDefinition, workflow_id)
            if wf is not None:
                run = db.exec(
                    select(WorkflowRun)
                    .where(WorkflowRun.workflow_id == wf.id)
                    .order_by(WorkflowRun.started_at.desc())
                ).first()
        if run is None and subject:
            wf = db.exec(
                select(WorkflowDefinition)
                .where(
                    WorkflowDefinition.tenant_id == (context.tenant_id or "default"),
                    WorkflowDefinition.name == f"onboard:{subject}",
                )
                .order_by(WorkflowDefinition.updated_at.desc())
            ).first()
            if wf is not None:
                run = db.exec(
                    select(WorkflowRun)
                    .where(WorkflowRun.workflow_id == wf.id)
                    .order_by(WorkflowRun.started_at.desc())
                ).first()

        if wf is None or run is None:
            return self._result(
                context,
                status="failed",
                summary="No onboarding workflow found",
                grounding="none",
                confidence=0.1,
            )

        try:
            steps = json.loads(wf.steps_json or "[]")
        except Exception:
            steps = []
        try:
            state = json.loads(run.steps_state_json or "{}")
        except Exception:
            state = {}

        per_system: list[dict[str, Any]] = []
        for s in steps:
            sid = s.get("id") or ""
            st = state.get(sid) or {}
            per_system.append(
                {
                    "step_id": sid,
                    "type": s.get("type"),
                    "resource_type": s.get("resource_type"),
                    "resource_id": s.get("resource_id"),
                    "status": st.get("status") or "pending",
                    "owner_username": s.get("owner_username"),
                }
            )

        return self._result(
            context,
            status="success",
            summary=(
                f"Onboarding {wf.name} run={run.id} status={run.status} "
                f"({len(per_system)} steps)"
            ),
            details={
                "workflow_id": wf.id,
                "workflow_run_id": run.id,
                "run_status": run.status,
                "per_system": per_system,
            },
            grounding="live",
            confidence=0.85,
        )


onboarding_agent = OnboardingAgent()
