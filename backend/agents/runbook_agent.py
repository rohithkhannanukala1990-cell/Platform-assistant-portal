"""Runbook agent — search and draft runbooks from grounded evidence only."""

from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from ..context import PlatformContext
from .base import AgentResult, BaseAgent

try:
    from ..database import Runbook  # type: ignore[attr-defined]
except ImportError:
    Runbook = None  # type: ignore[misc, assignment]

if Runbook is None:
    from ..routers.golden_paths import GoldenPathTemplate as Runbook  # type: ignore


def _detect_runbook_action(task: str, params: dict) -> str:
    text = (params.get("task") or params.get("message") or task or "").lower()
    if re.search(r"\bcreate|new|add|generate\b", text):
        return "create"
    if re.search(r"\bget|show|fetch\b", text):
        return "get"
    return "search"


def _runbook_row_to_dict(row) -> dict:
    steps = []
    raw_steps = getattr(row, "steps_json", None) or getattr(row, "content", None)
    if raw_steps:
        try:
            steps = json.loads(raw_steps) if isinstance(raw_steps, str) else raw_steps
        except json.JSONDecodeError:
            steps = [raw_steps]
    return {
        "id": getattr(row, "id", None),
        "name": getattr(row, "name", getattr(row, "title", "")),
        "description": getattr(row, "description", "") or "",
        "category": getattr(row, "category", "General"),
        "steps": steps,
    }


class RunbookAgent(BaseAgent):
    name = "runbook_agent"
    description = "Executes and drafts operational runbooks."
    requires_approval_envs = ["production"]
    primary_tools = ["Confluence", "Kubernetes", "Ansible", "GoldenPaths DB"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_runbook_action(task, params)
        query = params.get("query") or task
        runbooks: list = []
        evidence: list[dict] = []

        # Optional incident grounding
        incident_id = params.get("incident_id")
        if incident_id:
            evidence.append(
                self._evidence(
                    type="incident",
                    title=f"Incident {incident_id}",
                    source="params",
                    snippet=str(params.get("incident_summary") or incident_id),
                )
            )

        try:
            if action == "get" and params.get("runbook_id"):
                row = db.get(Runbook, params["runbook_id"])
                if row:
                    runbooks = [_runbook_row_to_dict(row)]
            elif action == "search":
                q = select(Runbook)
                if hasattr(Runbook, "is_active"):
                    q = q.where(Runbook.is_active == True)  # noqa: E712
                rows = db.exec(q).all()
                term = (query or "").lower()
                for row in rows:
                    d = _runbook_row_to_dict(row)
                    hay = f"{d['name']} {d['description']}".lower()
                    if not term or term in hay:
                        runbooks.append(d)
            elif action == "create":
                # Build generate plan only from DB golden-path / existing runbook evidence.
                q = select(Runbook)
                if hasattr(Runbook, "is_active"):
                    q = q.where(Runbook.is_active == True)  # noqa: E712
                for row in list(db.exec(q).all())[:20]:
                    d = _runbook_row_to_dict(row)
                    evidence.append(
                        self._evidence(
                            type="golden_path",
                            title=str(d.get("name") or d.get("id")),
                            source="golden_paths_db",
                            snippet=json.dumps(
                                {"id": d.get("id"), "category": d.get("category")},
                                default=str,
                            ),
                        )
                    )
                draft = None
                if evidence or incident_id:
                    try:
                        raw = await self._call_llm(
                            "Draft a runbook outline from EVIDENCE only. "
                            "Return JSON: summary, findings (steps), commands.",
                            context,
                            evidence=evidence,
                        )
                        draft = self._parse_llm_json(raw)
                    except Exception:
                        draft = None
                if not evidence:
                    evidence.append(
                        self._evidence(
                            type="plan",
                            title="Runbook create plan",
                            source="platform",
                            snippet=str(params.get("description") or query)[:500],
                        )
                    )
                return self._finalize_with_policy(
                    context,
                    summary=f"Create runbook: {params.get('name') or query[:60]}",
                    details={
                        "runbooks": [],
                        "matched_count": 0,
                        "query": query,
                        "action": "create",
                        "draft": draft,
                    },
                    commands=[],
                    evidence=evidence,
                    grounding="partial",
                    confidence=0.55,
                    task="create_runbook",
                    recommended_actions=[
                        {
                            "title": "Approve new runbook creation",
                            "risk": "low",
                            "requires_approval": True,
                        }
                    ],
                )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Runbook DB query failed",
                details={"error": str(exc)[:300], "query": query, "action": action},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        for rb in runbooks[:40]:
            evidence.append(
                self._evidence(
                    type="runbook",
                    title=str(rb.get("name") or rb.get("id")),
                    source="golden_paths_db",
                    snippet=json.dumps(
                        {
                            "id": rb.get("id"),
                            "category": rb.get("category"),
                            "description": (rb.get("description") or "")[:300],
                        },
                        default=str,
                    )[:1000],
                )
            )

        if not runbooks and action != "create":
            return self._result(
                context,
                status="success",
                summary=f"Runbook {action}: 0 match(es)",
                details={
                    "runbooks": [],
                    "matched_count": 0,
                    "query": query,
                    "empty": True,
                },
                evidence=[
                    self._evidence(
                        type="db_query",
                        title="Runbook search (empty)",
                        source="golden_paths_db",
                        snippet=f"query={query}",
                    )
                ],
                grounding="live",
                confidence=0.7,
            )

        return self._result(
            context,
            status="success",
            summary=f"Runbook {action}: {len(runbooks)} match(es)",
            details={
                "runbooks": runbooks[:50],
                "matched_count": len(runbooks),
                "query": query,
            },
            evidence=evidence,
            grounding="live",
            confidence=0.85,
        )


runbook_agent = RunbookAgent()
