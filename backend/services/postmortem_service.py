"""Postmortem generation from incident data, timeline, triage, and agent runs (Phase G3)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session, col, select

from ..ai.llm_service import llm_service
from ..db.core import engine
from ..db.models.ai_models import AgentRun
from ..db.models.ops import IncidentPostmortem
from ..db.repositories.incidents import get_incident
from .incident_timeline import enrich_incident_detail, synthesize_timeline

POSTMORTEM_MARKER = "POSTMORTEM_GENERATION_V1"

POSTMORTEM_SECTIONS = [
    "Summary",
    "Impact",
    "Detection",
    "Root cause",
    "What went well",
    "What went wrong",
    "Action items",
    "Timeline",
]

POSTMORTEM_SYSTEM_PROMPT = f"""You are a senior SRE writing an incident postmortem.
{POSTMORTEM_MARKER}

Return ONLY markdown with exactly these level-2 headings (in this order):
## Summary
## Impact
## Detection
## Root cause
## What went well
## What went wrong
## Action items
## Timeline

Rules:
- Use ONLY facts from the provided incident context JSON.
- For ## Timeline, reproduce ONLY the timeline events supplied — do NOT invent events, times, or actors.
- Each timeline bullet must match an event from the data (type, at, actor, detail).
- If data is missing for a narrative section, state that briefly rather than inventing.
- Action items should be concrete follow-ups grounded in evidence and triage data.
- No JSON fences. No extra top-level headings.
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if not markdown:
        return sections
    pattern = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        sections[title] = body
    return sections


def _serialize_postmortem(row: IncidentPostmortem) -> dict[str, Any]:
    try:
        sections = json.loads(row.sections_json or "{}")
    except (json.JSONDecodeError, TypeError, ValueError):
        sections = {}
    return {
        "id": row.id,
        "incident_id": row.incident_id,
        "tenant_id": row.tenant_id,
        "version": row.version,
        "markdown": row.markdown,
        "sections": sections if isinstance(sections, dict) else {},
        "generated_by": row.generated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def get_latest_postmortem(
    incident_id: int,
    *,
    tenant_id: str,
) -> dict[str, Any] | None:
    with Session(engine) as session:
        row = session.exec(
            select(IncidentPostmortem)
            .where(
                IncidentPostmortem.incident_id == incident_id,
                IncidentPostmortem.tenant_id == tenant_id,
            )
            .order_by(col(IncidentPostmortem.version).desc())
        ).first()
        return _serialize_postmortem(row) if row else None


def _fetch_agent_runs(incident_id: int, tenant_id: str) -> list[dict[str, Any]]:
    needle = f"incident #{incident_id}"
    out: list[dict[str, Any]] = []
    with Session(engine) as session:
        rows = session.exec(
            select(AgentRun)
            .where(AgentRun.tenant_id == tenant_id)
            .order_by(col(AgentRun.created_at).desc())
        ).all()
        for row in rows:
            task = (row.task or "").lower()
            if needle not in task and str(incident_id) not in (row.details_json or ""):
                continue
            try:
                details = json.loads(row.details_json or "{}")
            except (json.JSONDecodeError, TypeError, ValueError):
                details = {}
            out.append(
                {
                    "run_id": row.id,
                    "agent": row.agent,
                    "status": row.status,
                    "summary": row.summary,
                    "task": row.task,
                    "evidence": details.get("evidence") or [],
                    "grounding": details.get("grounding"),
                    "confidence": details.get("confidence"),
                    "recommended_actions": details.get("recommended_actions") or [],
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
            )
            if len(out) >= 10:
                break
    return out


def build_postmortem_context(incident: dict) -> dict[str, Any]:
    """Assemble grounded facts for LLM prompt — no invented timeline events."""
    detail = enrich_incident_detail(incident)
    timeline = synthesize_timeline(detail)
    return {
        "incident_id": detail.get("id"),
        "severity": detail.get("severity"),
        "summary": detail.get("summary"),
        "status": detail.get("status"),
        "root_cause": detail.get("root_cause"),
        "source": detail.get("source"),
        "timestamp": detail.get("timestamp"),
        "tenant_id": detail.get("tenant_id"),
        "workspace_id": detail.get("workspace_id"),
        "evidence": detail.get("evidence") or [],
        "action_plan": detail.get("action_plan") or [],
        "commands": detail.get("commands") or [],
        "proposed_remediation_plan": detail.get("proposed_remediation_plan") or [],
        "validation_steps": detail.get("validation_steps") or [],
        "execution_log": detail.get("execution_log"),
        "github_refs": detail.get("github_refs") or {},
        "timeline": timeline,
        "agent_runs": _fetch_agent_runs(
            int(detail.get("id") or 0),
            str(detail.get("tenant_id") or "default"),
        ),
    }


def _validate_sections(sections: dict[str, str]) -> list[str]:
    missing = []
    for name in POSTMORTEM_SECTIONS:
        if not (sections.get(name) or "").strip():
            missing.append(name)
    return missing


def _ensure_sections(markdown: str, context: dict[str, Any]) -> tuple[str, dict[str, str]]:
    sections = _parse_sections(markdown)
    missing = _validate_sections(sections)
    if not missing:
        return markdown, sections

    timeline_lines = []
    for ev in context.get("timeline") or []:
        timeline_lines.append(
            f"- **{ev.get('type', 'event')}** ({ev.get('at', '—')}) "
            f"— {ev.get('actor', 'system')}: {ev.get('detail', '')}"
        )
    timeline_body = "\n".join(timeline_lines) if timeline_lines else "No timeline events recorded."

    fallbacks = {
        "Summary": context.get("summary") or "No summary available.",
        "Impact": f"Severity: {context.get('severity') or 'Unknown'}. Status: {context.get('status') or 'OPEN'}.",
        "Detection": f"Detected via {context.get('source') or 'manual'} at {context.get('timestamp') or 'unknown time'}.",
        "Root cause": context.get("root_cause") or "Root cause not documented.",
        "What went well": "Review automated triage and response steps taken during the incident.",
        "What went wrong": "Document gaps based on evidence and unresolved action items.",
        "Action items": "\n".join(f"- {a}" for a in (context.get("action_plan") or [])[:5])
        or "- Complete follow-up remediation and monitoring improvements.",
        "Timeline": timeline_body,
    }
    for name in missing:
        sections[name] = fallbacks.get(name, "Not documented.")
    rebuilt = "\n\n".join(f"## {name}\n\n{sections[name]}" for name in POSTMORTEM_SECTIONS)
    return rebuilt, sections


async def generate_postmortem_markdown(context: dict[str, Any]) -> str:
    payload = json.dumps(context, default=str, indent=2)
    user_prompt = (
        "Generate a postmortem from this incident context JSON.\n"
        "Timeline section must list ONLY these events — do not add any others:\n\n"
        f"INCIDENT_CONTEXT_JSON:\n{payload}"
    )
    raw = await llm_service.chat(
        prompt=user_prompt,
        system_prompt=POSTMORTEM_SYSTEM_PROMPT,
        temperature=0.2,
        max_tokens=4096,
    )
    markdown, _ = _ensure_sections(raw or "", context)
    return markdown


def save_postmortem(
    incident_id: int,
    *,
    tenant_id: str,
    markdown: str,
    generated_by: str,
    sections: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    parsed = sections if sections is not None else _parse_sections(markdown)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        latest = session.exec(
            select(IncidentPostmortem)
            .where(
                IncidentPostmortem.incident_id == incident_id,
                IncidentPostmortem.tenant_id == tenant_id,
            )
            .order_by(col(IncidentPostmortem.version).desc())
        ).first()
        version = (latest.version + 1) if latest else 1
        row = IncidentPostmortem(
            incident_id=incident_id,
            tenant_id=tenant_id,
            version=version,
            markdown=markdown,
            sections_json=json.dumps(parsed, default=str),
            generated_by=generated_by,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize_postmortem(row)


def update_postmortem(
    incident_id: int,
    *,
    tenant_id: str,
    markdown: str,
    editor: str,
) -> dict[str, Any] | None:
    sections = _parse_sections(markdown)
    now = datetime.now(timezone.utc)
    with Session(engine) as session:
        row = session.exec(
            select(IncidentPostmortem)
            .where(
                IncidentPostmortem.incident_id == incident_id,
                IncidentPostmortem.tenant_id == tenant_id,
            )
            .order_by(col(IncidentPostmortem.version).desc())
        ).first()
        if not row:
            return None
        row.markdown = markdown
        row.sections_json = json.dumps(sections, default=str)
        row.generated_by = editor
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        return _serialize_postmortem(row)


async def generate_postmortem_for_incident(
    incident_id: int,
    *,
    tenant_id: str,
    actor: str,
) -> dict[str, Any]:
    incident = get_incident(incident_id, tenant_id=tenant_id)
    if not incident:
        raise ValueError("Incident not found")
    context = build_postmortem_context(incident)
    markdown = await generate_postmortem_markdown(context)
    sections = _parse_sections(markdown)
    return save_postmortem(
        incident_id,
        tenant_id=tenant_id,
        markdown=markdown,
        generated_by=actor,
        sections=sections,
    )
