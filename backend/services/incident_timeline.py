"""Incident timeline helpers and detail enrichment."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session

from ..db.core import engine
from ..db.models.ops import Incident


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timeline(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def append_timeline_event(
    incident_id: int,
    *,
    event_type: str,
    detail: str = "",
    actor: str = "system",
    meta: Optional[dict] = None,
) -> list[dict[str, Any]]:
    """Append a timeline event and return the full ordered timeline."""
    event = {
        "type": event_type,
        "at": _now_iso(),
        "actor": actor,
        "detail": detail,
        "meta": meta or {},
    }
    with Session(engine) as session:
        row = session.get(Incident, incident_id)
        if not row:
            raise ValueError(f"Incident {incident_id} not found")
        events = _parse_timeline(getattr(row, "timeline_json", None))
        events.append(event)
        row.timeline_json = json.dumps(events)
        session.add(row)
        session.commit()
    return sorted(events, key=lambda e: str(e.get("at") or ""))


def synthesize_timeline(incident: dict) -> list[dict[str, Any]]:
    """Build a timeline from stored events or synthesize from status fields."""
    stored = incident.get("timeline")
    if isinstance(stored, list) and stored:
        return sorted(stored, key=lambda e: str(e.get("at") or ""))

    raw_stored = incident.get("timeline_json")
    events = _parse_timeline(raw_stored if isinstance(raw_stored, str) else None)
    if events:
        return sorted(events, key=lambda e: str(e.get("at") or ""))

    ts = incident.get("timestamp") or _now_iso()
    out: list[dict[str, Any]] = [
        {
            "type": "detected",
            "at": ts,
            "actor": "system",
            "detail": f"Incident detected (source={incident.get('source') or 'manual'})",
            "meta": {},
        },
        {
            "type": "triaged",
            "at": ts,
            "actor": "ai",
            "detail": f"Triaged as {incident.get('severity') or 'Unknown'}: {incident.get('summary') or ''}"[:240],
            "meta": {"model_used": incident.get("model_used")},
        },
    ]
    plan = incident.get("proposed_remediation_plan") or []
    status = (incident.get("status") or "OPEN").upper()
    if plan or status in {
        "AWAITING_APPROVAL",
        "RESOLVED_BY_AGENT",
        "REJECTED",
        "ESCALATED_SECURITY_RISK",
    }:
        out.append(
            {
                "type": "actions_proposed",
                "at": ts,
                "actor": "agent",
                "detail": f"{len(plan) if isinstance(plan, list) else 0} remediation steps proposed",
                "meta": {"plan": plan if isinstance(plan, list) else []},
            }
        )
    if status == "RESOLVED_BY_AGENT":
        out.append(
            {
                "type": "approved",
                "at": ts,
                "actor": "operator",
                "detail": "Plan approved",
                "meta": {},
            }
        )
        out.append(
            {
                "type": "executed",
                "at": ts,
                "actor": "agent",
                "detail": "Remediation executed",
                "meta": {},
            }
        )
    elif status == "REJECTED":
        out.append(
            {
                "type": "rejected",
                "at": ts,
                "actor": "operator",
                "detail": "Plan rejected",
                "meta": {},
            }
        )
    elif status == "RESOLVED":
        out.append(
            {
                "type": "executed",
                "at": ts,
                "actor": "runbook",
                "detail": "Auto-remediation / runbook completed",
                "meta": {},
            }
        )
    elif status == "ESCALATED_SECURITY_RISK":
        out.append(
            {
                "type": "escalated",
                "at": ts,
                "actor": "guardrail",
                "detail": "Escalated due to security risk in proposed commands",
                "meta": {},
            }
        )
    return out


def parse_github_refs(incident: dict) -> dict[str, Any]:
    """Extract linked GitHub repo/PR/run refs from raw_logs when present."""
    refs: dict[str, Any] = {
        "repo": None,
        "pr_number": None,
        "run_id": None,
        "html_url": None,
        "delivery_id": None,
    }
    raw = incident.get("raw_logs") or ""
    try:
        data = json.loads(raw) if raw.strip().startswith("{") else None
    except (json.JSONDecodeError, TypeError, ValueError):
        data = None
    if isinstance(data, dict):
        refs["repo"] = data.get("repo") or None
        refs["pr_number"] = data.get("pr_number") or data.get("pr") or None
        refs["run_id"] = data.get("run_id") or None
        refs["html_url"] = data.get("html_url") or None
        refs["delivery_id"] = data.get("delivery_id") or None
        return refs

    m_repo = re.search(r"repo=([\w.-]+/[\w.-]+)", raw)
    if m_repo:
        refs["repo"] = m_repo.group(1)
    m_pr = re.search(r"\bpr[=#]?(\d+)\b", raw, re.I)
    if m_pr:
        refs["pr_number"] = int(m_pr.group(1))
    m_run = re.search(r"run_id[=:]?\s*(\d+)", raw, re.I)
    if m_run:
        refs["run_id"] = int(m_run.group(1))
    m_url = re.search(r"https://github\.com/[^\s\"']+", raw)
    if m_url:
        refs["html_url"] = m_url.group(0)
    return refs


def pending_approval_payload(incident: dict) -> dict[str, Any] | None:
    status = (incident.get("status") or "").upper()
    if status not in {"AWAITING_APPROVAL", "ESCALATED_SECURITY_RISK"}:
        return None
    plan = incident.get("proposed_remediation_plan") or []
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except Exception:
            plan = [plan]
    return {
        "status": status,
        "owner_role": incident.get("owner_role") or "Admin",
        "proposed_remediation_plan": plan if isinstance(plan, list) else [],
        "requires_approval": status == "AWAITING_APPROVAL",
        "escalated": status == "ESCALATED_SECURITY_RISK",
    }


def extract_executable_commands(plan: list | str | None, fallback_commands: list | None = None) -> list[str]:
    items: list[str] = []
    if isinstance(plan, str):
        try:
            plan = json.loads(plan)
        except Exception:
            plan = [plan]
    if isinstance(plan, list):
        for s in plan:
            text = str(s).strip()
            if not text:
                continue
            if text.lower().startswith("run:"):
                items.append(text.split(":", 1)[1].strip())
            elif any(tok in text for tok in ("kubectl ", "docker ", "git ", "helm ", "aws ")):
                items.append(text)
    if not items and fallback_commands:
        items = [str(c).strip() for c in fallback_commands if str(c).strip()]
    return items[:20]


def enrich_incident_detail(incident: dict) -> dict[str, Any]:
    """Attach timeline, github_refs, pending_approval, execution_log for command center."""
    detail = dict(incident)
    detail["timeline"] = synthesize_timeline(incident)
    detail["github_refs"] = parse_github_refs(incident)
    detail["pending_approval"] = pending_approval_payload(incident)
    detail["execution_log"] = (
        incident.get("agent_execution_logs")
        or incident.get("execution_logs")
        or None
    )
    return detail
