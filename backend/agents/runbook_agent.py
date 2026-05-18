"""Runbook agent — search and manage operational runbooks."""

from __future__ import annotations

import json
import re

from sqlmodel import Session, select

from ..context import PlatformContext
from .base import BaseAgent

try:
    from ..database import Runbook  # type: ignore[attr-defined]
except ImportError:
    Runbook = None  # type: ignore[misc, assignment]

if Runbook is None:
    from ..routers.golden_paths import GoldenPathTemplate as Runbook  # type: ignore


def _detect_runbook_action(task: str, params: dict) -> str:
    text = (params.get("task") or params.get("message") or task or "").lower()
    if re.search(r"\bcreate|new|add\b", text):
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
    primary_tools = ["Confluence", "Kubernetes", "Ansible"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        action = _detect_runbook_action(task, params)
        query = params.get("query") or task
        runbooks: list = []

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
                term = query.lower()
                for row in rows:
                    d = _runbook_row_to_dict(row)
                    hay = f"{d['name']} {d['description']}".lower()
                    if not term or term in hay:
                        runbooks.append(d)
            elif action == "create":
                return self._build_result(
                    context,
                    status="pending_approval",
                    summary=f"Create runbook: {params.get('name') or query[:60]}",
                    details={
                        "runbooks": [],
                        "matched_count": 0,
                        "query": query,
                        "action": "create",
                    },
                    requires_approval=True,
                    approval_payload={
                        "action": "create_runbook",
                        "name": params.get("name") or "New runbook",
                        "description": params.get("description") or query,
                    },
                )
        except Exception:
            runbooks = []

        return self._build_result(
            context,
            status="success",
            summary=f"Runbook {action}: {len(runbooks)} match(es)",
            details={
                "runbooks": runbooks[:50],
                "matched_count": len(runbooks),
                "query": query,
            },
        )


runbook_agent = RunbookAgent()
