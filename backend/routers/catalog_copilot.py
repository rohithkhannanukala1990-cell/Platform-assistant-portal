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
from .scorecards import ScorecardCheck
from .standards import EntityStandardEvaluation

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


def _std_bucket(status: str | None) -> str:
    s = (status or "").lower()
    if s in ("pass", "passed"):
        return "passed"
    if s in ("fail", "failed"):
        return "failed"
    return "warnings"


def _build_entity_context(
    session: Session,
    entity: CatalogEntity,
    entity_id: str,
) -> tuple[str, list[str], list[ScorecardCheck]]:
    """Build grounded context lines and track scorecard rows for fallback."""
    context_parts: list[str] = []
    data_sources: list[str] = ["entity"]

    context_parts.append(f"Entity: {entity.name} ({entity.kind})")
    context_parts.append(f"Lifecycle: {entity.lifecycle or 'unknown'}")
    context_parts.append(f"Owner: {entity.owner_team or 'unknown'}")
    context_parts.append(f"Health: {entity.health_status or 'unknown'}")
    context_parts.append(f"Description: {entity.description or 'none'}")
    context_parts.append(f"Language: {entity.language or 'unknown'}")

    scorecard_rows = list(
        session.exec(
            select(ScorecardCheck).where(ScorecardCheck.entity_id == entity_id)
        ).all()
    )
    if scorecard_rows:
        overall = round(sum(r.score for r in scorecard_rows) / len(scorecard_rows))
        context_parts.append(f"Scorecard overall: {overall}/100")
        fails = [r.check_name for r in scorecard_rows if r.status == "fail"]
        warns = [r.check_name for r in scorecard_rows if r.status == "warn"]
        if fails:
            context_parts.append(f"Failing checks: {', '.join(fails)}")
        if warns:
            context_parts.append(f"Warning checks: {', '.join(warns)}")
        data_sources.append("scorecards")
    else:
        context_parts.append("Scorecard: not yet evaluated")

    std_evals = session.exec(
        select(EntityStandardEvaluation).where(
            EntityStandardEvaluation.entity_id == entity_id
        )
    ).all()
    if std_evals:
        passed = sum(1 for e in std_evals if _std_bucket(e.status) == "passed")
        failed = sum(1 for e in std_evals if _std_bucket(e.status) == "failed")
        warnings = sum(1 for e in std_evals if _std_bucket(e.status) == "warnings")
        context_parts.append(
            f"Standards: {passed} passed, {failed} failed, {warnings} warning"
        )
        data_sources.append("standards")
    else:
        context_parts.append("Standards: not yet evaluated")

    name_lower = entity.name.lower()
    incidents = [
        i
        for i in session.exec(select(Incident)).all()
        if name_lower in (i.summary or "").lower()
    ][:5]
    if incidents:
        inc_text = "\n".join(
            f"  - [{i.severity}] {i.summary} ({i.status})" for i in incidents
        )
        context_parts.append(f"Recent incidents:\n{inc_text}")
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
                label, other = "Depends on", d.to_entity_id
            else:
                label, other = "Used by", d.from_entity_id
            dep_lines.append(f"  - {label}: {entities_map.get(other, other)} ({d.dep_type})")
        context_parts.append("Dependencies:\n" + "\n".join(dep_lines))
        data_sources.append("dependencies")

    return "\n".join(context_parts), data_sources, scorecard_rows


def _fallback_response(
    context: str,
    scorecard_rows: list[ScorecardCheck],
    entity_name: str | None,
    data_sources: list[str],
) -> CopilotResponse:
    fails = [r.check_name for r in scorecard_rows if r.status == "fail"]
    return CopilotResponse(
        answer=(
            "AI is temporarily unavailable. Based on available data: "
            + (context[:500] + ("…" if len(context) > 500 else ""))
        ),
        risks=fails or ["Scorecard or standards data may be incomplete"],
        recommended_actions=["Run scorecard evaluation", "Assign owner team"],
        suggested_workflows=[],
        entity_name=entity_name,
        data_sources_used=data_sources,
    )


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

    scorecard_rows: list[ScorecardCheck] = []

    if entity_id:
        entity = session.get(CatalogEntity, entity_id)
        if not entity or not entity.is_active:
            raise HTTPException(status_code=404, detail="Entity not found")

        context_string, data_sources, scorecard_rows = _build_entity_context(
            session, entity, entity_id
        )
        context_parts = [context_string]

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

    context_string = (
        context_parts[0]
        if len(context_parts) == 1 and entity_id
        else ("\n\n".join(context_parts) if context_parts else "No entity data available.")
    )

    prompt = f"""You are an AI assistant for an Internal Developer Portal.
Answer ONLY from the data provided. Do not guess or hallucinate.

SERVICE DATA:
{context_string}

USER QUESTION: {request.question.strip()}

Respond in this exact JSON format, nothing else:
{{
  "answer": "2-3 sentence direct answer",
  "risks": ["risk 1", "risk 2"],
  "recommended_actions": ["action name 1", "action name 2"],
  "suggested_workflows": ["workflow name 1"]
}}
Return only valid JSON. No markdown fences. No explanation."""

    system_prompt = COPILOT_SYSTEM_SUFFIX + context_string
    model = (os.getenv("AI_DEFAULT_MODEL", "gemini-1.5-flash") or "gemini-1.5-flash").strip()

    try:
        raw_response = await llm_router.chat(
            [{"role": "user", "content": prompt}],
            model=model,
            system_prompt=system_prompt,
        )
    except Exception:
        return _fallback_response(
            context_string,
            scorecard_rows,
            entity.name if entity else None,
            data_sources,
        )

    try:
        parsed = _parse_copilot_json(raw_response)
        return CopilotResponse(
            answer=str(parsed.get("answer") or raw_response),
            risks=[str(x) for x in (parsed.get("risks") or [])],
            recommended_actions=[str(x) for x in (parsed.get("recommended_actions") or [])],
            suggested_workflows=[str(x) for x in (parsed.get("suggested_workflows") or [])],
            entity_name=entity.name if entity else None,
            data_sources_used=data_sources,
        )
    except json.JSONDecodeError:
        return _fallback_response(
            context_string,
            scorecard_rows,
            entity.name if entity else None,
            data_sources,
        )
