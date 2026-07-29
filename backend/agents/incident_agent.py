"""Incident agent — PagerDuty incident lifecycle (grounded)."""

from __future__ import annotations

import json
import re

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


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


def _extract_incident_id(text: str) -> str | None:
    m = re.search(r"(?:incident[_\s-]*)?([A-Z0-9]{7,})", text, re.I)
    return m.group(1) if m else None


class IncidentAgent(BaseAgent):
    name = "incident_agent"
    description = "Incident triage, paging, and remediation coordination."
    requires_approval_envs = ["production"]
    primary_tools = ["PagerDuty", "OpsGenie", "Kubernetes"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_action(task, params)
        pd = await self._ground_pd(context, db)
        if pd is None:
            return self._no_data_result(
                context,
                "PagerDuty not connected. Connect a PagerDuty account in Tool Registry.",
                missing_tools=["PagerDuty"],
                details={"action_taken": action, "incidents": [], "count": 0},
            )

        incidents: list = []
        action_taken = action
        evidence: list[dict] = []
        write_actions = {"create", "acknowledge", "resolve"}

        try:
            if action == "list_open":
                incidents = await pd.list_incidents(status="triggered", limit=20)
            elif action == "create":
                if self._should_require_approval(context):
                    title = params.get("title") or task[:120] or "Platform incident"
                    return self._result(
                        context,
                        status="pending_approval",
                        summary=f"Production create incident requires approval: {title}",
                        details={
                            "incidents": [],
                            "action_taken": "create",
                            "count": 0,
                        },
                        requires_approval=True,
                        approval_payload={
                            "action": "create",
                            "title": title,
                            "service_id": params.get("service_id") or "",
                            "urgency": params.get("urgency", "high"),
                        },
                        grounding="partial",
                        confidence=0.5,
                        evidence=[
                            self._evidence(
                                type="plan",
                                title="Create PagerDuty incident (pending approval)",
                                source="pagerduty",
                                snippet=title,
                            )
                        ],
                    )
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
                    return self._result(
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
                        grounding="partial",
                        confidence=0.7,
                        evidence=[
                            self._evidence(
                                type="incident",
                                title=f"Incident {incident_id}",
                                source="pagerduty",
                                snippet=f"Pending {action} in production",
                            )
                        ],
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
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary=f"PagerDuty {action} failed",
                details={
                    "incidents": [],
                    "action_taken": action,
                    "count": 0,
                    "error": str(exc)[:300],
                },
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        for inc in incidents:
            iid = inc.get("id") or inc.get("incident_id") or ""
            evidence.append(
                self._evidence(
                    type="incident",
                    title=str(inc.get("title") or f"Incident {iid}"),
                    source="pagerduty",
                    url=inc.get("html_url"),
                    snippet=json.dumps(
                        {
                            "id": iid,
                            "status": inc.get("status"),
                            "urgency": inc.get("urgency"),
                            "service": (inc.get("service") or {}).get("summary")
                            if isinstance(inc.get("service"), dict)
                            else inc.get("service"),
                        },
                        default=str,
                    )[:1000],
                )
            )

        if action in write_actions and self._should_require_approval(context):
            # Defensive: write paths should already have returned pending_approval above.
            pass

        return self._result(
            context,
            status="success",
            summary=f"Incident {action_taken}: {len(incidents)} record(s)",
            details={
                "incidents": incidents,
                "action_taken": action_taken,
                "count": len(incidents),
            },
            evidence=evidence,
            grounding="live",
            confidence=0.85 if incidents else 0.7,
        )


incident_agent = IncidentAgent()
