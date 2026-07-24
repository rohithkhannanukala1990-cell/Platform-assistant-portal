"""Incident agent — PagerDuty incident lifecycle."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..context import PlatformContext
from ..services.pagerduty_access import try_pagerduty_connector_from_context
from .base import BaseAgent


def _detect_action(task: str, params: dict) -> str:
    text = (params.get("task") or params.get("message") or task or "").lower()
    if re.search(r"\blist|open|show\b", text):
        return "list_open"
    if re.search(r"\backnowledge|ack\b", text):
        return "acknowledge"
    if re.search(r"\bcreate|new|page\b", text):
        return "create"
    if re.search(r"\bresolve|close\b", text):
        return "resolve"
    return params.get("action") or "list_open"


class IncidentAgent(BaseAgent):
    name = "incident_agent"
    description = "Incident triage, paging, and remediation coordination."
    requires_approval_envs = ["production"]
    primary_tools = ["PagerDuty", "OpsGenie", "Kubernetes"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_action(task, params)
        pd = try_pagerduty_connector_from_context(context, db=db)
        if pd is None:
            return self._build_result(
                context,
                status="skipped",
                summary="PagerDuty not connected. Connect a PagerDuty account in Tool Registry.",
                details={
                    "incidents": [],
                    "action_taken": action,
                    "count": 0,
                    "reason": "pagerduty_not_configured",
                },
            )

        incidents: list = []
        action_taken = action

        try:
            if action == "list_open":
                incidents = await pd.list_incidents(status="triggered", limit=20)
            elif action == "create":
                result = await pd.create_incident(
                    title=params.get("title") or task[:120] or "Platform incident",
                    service_id=params.get("service_id") or "",
                    urgency=params.get("urgency", "high"),
                )
                if result.get("id"):
                    incidents = [result]
                    action_taken = "created"
            elif action in ("acknowledge", "resolve"):
                incident_id = params.get("incident_id") or _extract_incident_id(task)
                if context.is_production() and incident_id:
                    return self._build_result(
                        context,
                        status="pending_approval",
                        summary=f"Production {action} for incident {incident_id} requires approval",
                        details={
                            "incidents": [{"id": incident_id}],
                            "action_taken": action,
                            "count": 1,
                        },
                        requires_approval=True,
                        approval_payload={
                            "action": action,
                            "incident_id": incident_id,
                        },
                    )
                if incident_id:
                    if action == "acknowledge":
                        await pd.acknowledge_incident(incident_id)
                    else:
                        await pd.resolve_incident(incident_id)
                    incidents = [{"id": incident_id, "status": action}]
                    action_taken = action
                else:
                    incidents = await pd.list_incidents(status="triggered", limit=5)
            else:
                incidents = await pd.list_incidents(status="triggered", limit=20)
        except Exception:
            incidents = []

        return self._build_result(
            context,
            status="success",
            summary=f"Incident {action_taken}: {len(incidents)} record(s)",
            details={
                "incidents": incidents,
                "action_taken": action_taken,
                "count": len(incidents),
            },
        )


def _extract_incident_id(text: str) -> str | None:
    m = re.search(r"(?:incident[_\s-]*)?([A-Z0-9]{7,})", text, re.I)
    return m.group(1) if m else None


incident_agent = IncidentAgent()
