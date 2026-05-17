"""Catalog entity copilot — grounded AI answers for a single catalog entity."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..ai.llm_router import llm_router
from ..auth import User, get_current_user, get_session
from ..database import Incident
from .catalog import CatalogEntity, ServiceDependency
from .entity_actions import EntityActionRun
from .scorecards import ScorecardCheck
from .standards import EntityStandardEvaluation, Standard

router = APIRouter(prefix="/api/catalog-copilot", tags=["catalog-copilot"])

COPILOT_SYSTEM_SUFFIX = (
    "You are a platform engineering assistant for an Internal Developer Portal. "
    "You have access to the following real data about a service. "
    "Answer the user's question using ONLY the data provided below. "
    "If data is missing or insufficient, say so explicitly — do not invent facts. "
    "Be concise, practical, and actionable. "
    "Return your response as valid JSON with these exact keys:\n"
    "{\n"
    '  "answer": "brief direct answer to the question",\n'
    '  "risks": ["list of specific risks identified from data"],\n'
    '  "recommended_actions": ["list of concrete next steps"],\n'
    '  "suggested_workflows": ["Golden Path or workflow names that apply"]\n'
    "}\n\n"
    "Return ONLY the JSON object. No markdown fences.\n\n"
    "=== PLATFORM DATA ===\n"
)


class CopilotRequest(BaseModel):
    question: str
    entity_id: Optional[str] = None
    team: Optional[str] = None


class CopilotResponse(BaseModel):
    answer: str
    risks: list[str] = []
    recommended_actions: list[str] = []
    suggested_workflows: list[str] = []
    entity_name: Optional[str] = None
    data_sources_used: list[str] = []


def _parse_copilot_json(raw: str) -> dict[str, Any]:
    clean = (raw or "").strip()
    if "```" in clean:
        for block in re.findall(r"```(?:json)?\s*([\s\S]*?)```", clean, re.IGNORECASE):
            block = block.strip()
            if block.startswith("{"):
                clean = block
                break
        else:
            parts = clean.split("```")
            for part in parts:
                p = part.strip()
                if p.lower().startswith("json"):
                    p = p[4:].strip()
                if p.startswith("{"):
                    clean = p
                    break
    match = re.search(r"\{[\s\S]*\}", clean)
    if match:
        clean = match.group(0)
    return json.loads(clean)


def _status_label(status: str | None) -> str:
    return (status or "unknown").upper()


@router.post("/copilot", response_model=CopilotResponse)
async def catalog_copilot(
    request: CopilotRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if not (request.question or "").strip():
        raise HTTPException(status_code=400, detail="question is required")

    context_parts: list[str] = []
    data_sources: list[str] = []
    entity: CatalogEntity | None = None
    entity_id = (request.entity_id or "").strip() or None

    if entity_id:
        entity = session.get(CatalogEntity, entity_id)
        if not entity or not entity.is_active:
            raise HTTPException(status_code=404, detail="Entity not found")

        context_parts.append(
            f"SERVICE: {entity.name}\n"
            f"  Kind: {entity.kind}\n"
            f"  Owner Team: {entity.owner_team or 'Unknown'}\n"
            f"  Lifecycle: {entity.lifecycle or 'Unknown'}\n"
            f"  Health: {entity.health_status or 'Unknown'}\n"
            f"  Language: {entity.language or '—'}\n"
            f"  Description: {entity.description or 'No description'}"
        )
        data_sources.append("entity")

        checks = session.exec(
            select(ScorecardCheck)
            .where(ScorecardCheck.entity_id == entity_id)
            .order_by(ScorecardCheck.evaluated_at.desc())
            .limit(20)
        ).all()
        if checks:
            checks_text = "\n".join(
                f"  - [{_status_label(c.status)}] {c.check_name}"
                f"{f' (score: {c.score})' if c.score is not None else ''}"
                + (f" — {c.rationale[:120]}" if c.rationale else "")
                for c in checks
            )
            context_parts.append(f"SCORECARD RESULTS:\n{checks_text}")
            data_sources.append("scorecards")

        std_evals = session.exec(
            select(EntityStandardEvaluation)
            .where(EntityStandardEvaluation.entity_id == entity_id)
            .order_by(EntityStandardEvaluation.evaluated_at.desc())
            .limit(20)
        ).all()
        if std_evals:
            standards_map = {s.id: s for s in session.exec(select(Standard)).all()}
            evals_text = "\n".join(
                f"  - [{_status_label(ev.status)}] "
                f"{standards_map[ev.standard_id].name if ev.standard_id in standards_map else ev.standard_id}"
                f" (overall_score: {ev.overall_score})"
                for ev in std_evals
            )
            context_parts.append(f"STANDARDS EVALUATION:\n{evals_text}")
            data_sources.append("standards")

        name_lower = entity.name.lower()
        all_incidents = session.exec(select(Incident)).all()
        incidents = [
            i
            for i in all_incidents
            if name_lower in (i.summary or "").lower()
        ][:5]
        if incidents:
            inc_text = "\n".join(
                f"  - [{i.severity}] {i.summary} ({i.status})"
                for i in incidents
            )
            context_parts.append(f"RECENT INCIDENTS:\n{inc_text}")
            data_sources.append("incidents")

        entities_map = {
            e.id: e.name
            for e in session.exec(
                select(CatalogEntity).where(CatalogEntity.is_active == 1)
            ).all()
        }
        deps = session.exec(
            select(ServiceDependency).where(
                (ServiceDependency.from_entity_id == entity_id)
                | (ServiceDependency.to_entity_id == entity_id)
            ).limit(10)
        ).all()
        if deps:
            dep_lines = []
            for d in deps:
                if d.from_entity_id == entity_id:
                    other = d.to_entity_id
                    label = "Depends on"
                else:
                    other = d.from_entity_id
                    label = "Used by"
                dep_lines.append(
                    f"  - {label}: {entities_map.get(other, other)} ({d.dep_type})"
                )
            context_parts.append(f"DEPENDENCIES:\n" + "\n".join(dep_lines))
            data_sources.append("dependencies")

        action_runs = session.exec(
            select(EntityActionRun)
            .where(EntityActionRun.entity_id == entity_id)
            .order_by(EntityActionRun.created_at.desc())
            .limit(5)
        ).all()
        if action_runs:
            runs_text = "\n".join(
                f"  - [{r.status}] action_id={r.action_id} by {r.requested_by}"
                for r in action_runs
            )
            context_parts.append(f"RECENT ENTITY ACTIONS:\n{runs_text}")
            data_sources.append("actions")

    elif request.team:
        team_entities = session.exec(
            select(CatalogEntity).where(CatalogEntity.is_active == 1)
        ).all()
        team_entities = [
            e for e in team_entities if (e.owner_team or "").strip() == request.team.strip()
        ]
        if team_entities:
            names = ", ".join(e.name for e in team_entities[:15])
            context_parts.append(
                f"TEAM: {request.team}\nServices ({len(team_entities)}): {names}"
            )
            data_sources.append("team")

    context_string = "\n\n".join(context_parts) if context_parts else "No entity data available."
    system_prompt = COPILOT_SYSTEM_SUFFIX + context_string
    user_message = request.question.strip()
    model = (os.getenv("AI_DEFAULT_MODEL", "gemini-1.5-flash") or "gemini-1.5-flash").strip()

    try:
        raw_response = await llm_router.chat(
            [{"role": "user", "content": user_message}],
            model=model,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI provider error: {exc}") from exc

    try:
        parsed = _parse_copilot_json(raw_response)
        return CopilotResponse(
            answer=parsed.get("answer", raw_response),
            risks=list(parsed.get("risks") or []),
            recommended_actions=list(parsed.get("recommended_actions") or []),
            suggested_workflows=list(parsed.get("suggested_workflows") or []),
            entity_name=entity.name if entity else None,
            data_sources_used=data_sources,
        )
    except json.JSONDecodeError:
        return CopilotResponse(
            answer=raw_response,
            entity_name=entity.name if entity else None,
            data_sources_used=data_sources,
        )
