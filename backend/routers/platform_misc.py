"""Settings, analytics, chat, search, anomaly scan, and DB query analysis."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text as sa_text
from sqlmodel import Session, select

from ..ai.ai_utils import ask_ai, call_llm
from ..auth import User, get_current_user
from ..database import (
    CICDPipeline,
    Incident,
    InfraGeneration,
    Tool,
    create_notification,
    engine as db_engine,
    get_all_cicd,
    get_all_incidents,
    get_all_infra,
    get_all_notifications,
    get_settings,
    save_incident,
    serialize_incident,
    update_settings,
)
from ..rate_limit import limiter
from ..services.demo_fixtures import ANOMALY_INCIDENT, demo_data_enabled
from ..services.incidents_service import hitl_evaluate as _hitl_evaluate

router = APIRouter(tags=["platform"])


@router.get("/api/settings")
def fetch_settings(current_user: User = Depends(get_current_user)):
    return get_settings()


@router.post("/api/settings")
@limiter.limit("5/minute")
def save_settings(request: Request, body: dict, current_user: User = Depends(get_current_user)):
    return update_settings(body)


@router.get("/api/analytics")
def get_analytics(current_user: User = Depends(get_current_user)):
    incidents = get_all_incidents()
    infra_list = get_all_infra()
    cicd_list = get_all_cicd()
    notifs = get_all_notifications()

    total_incidents = len(incidents)
    critical_alerts = sum(1 for i in incidents if i["severity"] == "Critical")
    unread_notifs = sum(1 for n in notifs if not n["is_read"])

    severity_order = ["Critical", "High", "Medium", "Warning", "Low", "Unknown"]
    sev_counter = Counter(i["severity"] for i in incidents)
    incidents_by_severity = [
        {"name": s, "value": sev_counter.get(s, 0)}
        for s in severity_order
        if sev_counter.get(s, 0) > 0
    ]

    src_counter = Counter(
        (i.get("source") or "manual").replace("webhook:", "") for i in incidents
    )
    top_sources = [{"name": src, "value": cnt} for src, cnt in src_counter.most_common(8)]

    now = datetime.now(timezone.utc)
    days = [(now - timedelta(days=i)).strftime("%b %d") for i in range(6, -1, -1)]
    day_counter: dict[str, int] = {d: 0 for d in days}
    for inc in incidents:
        try:
            ts = datetime.fromisoformat(inc["timestamp"])
            key = ts.strftime("%b %d")
            if key in day_counter:
                day_counter[key] += 1
        except Exception:
            pass
    incidents_over_time = [{"date": d, "count": day_counter[d]} for d in days]

    module_activity = [
        {"name": "Alerts", "value": total_incidents},
        {"name": "Infra", "value": len(infra_list)},
        {"name": "CI/CD", "value": len(cicd_list)},
    ]

    mttr_display = "N/A"
    if len(incidents) >= 2:
        try:
            sorted_ts = sorted(datetime.fromisoformat(i["timestamp"]) for i in incidents)
            gaps = [
                (sorted_ts[j + 1] - sorted_ts[j]).total_seconds() / 60
                for j in range(len(sorted_ts) - 1)
            ]
            avg_gap = sum(gaps) / len(gaps)
            if avg_gap < 60:
                mttr_display = f"{int(avg_gap)}m"
            else:
                mttr_display = f"{avg_gap / 60:.1f}h"
        except Exception:
            pass

    return {
        "total_incidents": total_incidents,
        "critical_alerts": critical_alerts,
        "unread_notifications": unread_notifs,
        "total_infra": len(infra_list),
        "total_cicd": len(cicd_list),
        "mttr": mttr_display,
        "incidents_by_severity": incidents_by_severity,
        "top_sources": top_sources,
        "incidents_over_time": incidents_over_time,
        "module_activity": module_activity,
    }


CHAT_SYSTEM_TEMPLATE = """You are an SRE Platform Assistant embedded in an AIOps portal.

Current system state:
{context}

Rules:
- Answer ONLY based on the data provided above. Do not invent data.
- Be concise — 2-4 sentences max unless a list is clearly better.
- If the user asks something completely unrelated to platform operations, politely decline.
- Use plain text. No markdown headers, no bullet asterisks.
- If referencing an incident, include its ID and severity.
"""


class ChatRequest(BaseModel):
    message: str


def _build_context() -> str:
    incidents = get_all_incidents()
    infra_list = get_all_infra()
    cicd_list = get_all_cicd()
    notifs = get_all_notifications()

    open_incidents = [i for i in incidents if i.get("status", "OPEN") == "OPEN"]
    resolved_incidents = [i for i in incidents if i.get("status", "OPEN") == "RESOLVED"]
    critical_open = [i for i in open_incidents if i["severity"] == "Critical"]

    lines = [
        f"Total incidents: {len(incidents)}",
        f"Open incidents: {len(open_incidents)}",
        f"Resolved incidents: {len(resolved_incidents)}",
        f"Critical open incidents: {len(critical_open)}",
    ]

    if open_incidents:
        lines.append("Open incident summaries:")
        for i in open_incidents[:5]:
            lines.append(f"  - Incident #{i['id']} [{i['severity']}]: {i['summary'][:120]}")

    if resolved_incidents:
        lines.append("Last resolved incidents:")
        for i in resolved_incidents[:3]:
            lines.append(
                f"  - Incident #{i['id']} [{i['severity']}]: {i['summary'][:100]} (RESOLVED)"
            )

    lines.append(f"Infra generations in DB: {len(infra_list)}")
    if infra_list:
        last_infra = infra_list[0]
        lines.append(f"  Last: {last_infra['resource_name']} on {last_infra['provider_used']}")

    lines.append(f"CI/CD pipelines in DB: {len(cicd_list)}")
    if cicd_list:
        last_cicd = cicd_list[0]
        lines.append(f"  Last: {last_cicd['tool_name']} pipeline")

    unread = sum(1 for n in notifs if not n["is_read"])
    lines.append(f"Unread notifications: {unread}")

    return "\n".join(lines)


@router.post("/api/chat")
@limiter.limit("10/minute")
async def platform_chat(
    request: Request,
    chat_in: ChatRequest,
    current_user: User = Depends(get_current_user),
):
    if not chat_in.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    context = _build_context()
    system_prompt = CHAT_SYSTEM_TEMPLATE.format(context=context)

    try:
        response = await call_llm(chat_in.message, system_prompt=system_prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI provider error: {str(exc)}")

    return {"response": response.strip()}


@router.get("/api/search")
def unified_search(
    q: str = "",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """Search across catalog entities, incidents, tools, cicd, infra."""
    if not q.strip() or len(q.strip()) < 2:
        return []

    term = f"%{q.strip().lower()}%"
    results = []

    with Session(db_engine) as session:
        try:
            from .catalog import CatalogEntity

            cats = session.exec(
                select(CatalogEntity)
                .where(
                    CatalogEntity.is_active == 1,
                    sa_text(
                        "LOWER(name) LIKE :t OR LOWER(owner_team) LIKE :t OR "
                        "LOWER(COALESCE(description, '')) LIKE :t"
                    ),
                )
                .limit(5),
                params={"t": term},
            ).all()
            for c in cats:
                results.append(
                    {
                        "type": "Catalog",
                        "id": c.id,
                        "title": c.name,
                        "subtitle": f"{c.kind} · {c.owner_team}",
                        "url": "/catalog",
                    }
                )
        except Exception:
            pass

        try:
            from ..database import Workspace

            tenant_id = getattr(current_user, "tenant_id", None) or "default"
            spaces = session.exec(
                select(Workspace)
                .where(
                    Workspace.is_active == 1,
                    Workspace.tenant_id == tenant_id,
                    sa_text(
                        "LOWER(name) LIKE :t OR LOWER(COALESCE(description, '')) LIKE :t"
                    ),
                )
                .limit(5),
                params={"t": term},
            ).all()
            for w in spaces:
                results.append(
                    {
                        "type": "Workspace",
                        "id": w.id,
                        "title": w.name,
                        "subtitle": w.description or w.environment,
                        "url": "/workspaces",
                    }
                )
        except Exception:
            pass

        try:
            from ..agents import list_agents

            needle = q.strip().lower()
            for agent in list_agents():
                if needle in (agent.get("name") or "").lower() or needle in (
                    agent.get("description") or ""
                ).lower():
                    results.append(
                        {
                            "type": "Agent",
                            "id": agent["name"],
                            "title": agent["name"],
                            "subtitle": (agent.get("description") or "")[:60],
                            "url": "/agents",
                        }
                    )
                if len([r for r in results if r["type"] == "Agent"]) >= 5:
                    break
        except Exception:
            pass

        incidents = session.exec(
            select(Incident)
            .where(sa_text("LOWER(summary) LIKE :t OR LOWER(root_cause) LIKE :t"))
            .order_by(Incident.timestamp.desc())
            .limit(min(limit, 10)),
            params={"t": term},
        ).all()
        for i in incidents:
            results.append(
                {
                    "type": "Incident",
                    "id": str(i.id),
                    "title": (i.summary or "")[:80],
                    "subtitle": f"{i.severity or '?'} · {i.status or '?'}",
                    "url": "/incidents",
                }
            )
            if len(results) >= limit:
                return results[:limit]

        tools = session.exec(
            select(Tool).where(sa_text("LOWER(name) LIKE :t OR LOWER(category) LIKE :t")).limit(5),
            params={"t": term},
        ).all()
        for t_row in tools:
            results.append(
                {
                    "type": "Tool",
                    "id": t_row.id,
                    "title": t_row.name,
                    "subtitle": t_row.category,
                    "url": "/tools",
                }
            )

        infra_rows = session.exec(
            select(InfraGeneration)
            .where(sa_text("LOWER(resource_name) LIKE :t"))
            .order_by(InfraGeneration.timestamp.desc())
            .limit(5),
            params={"t": term},
        ).all()
        for item in infra_rows:
            results.append(
                {
                    "type": "Infra",
                    "id": str(item.id or ""),
                    "title": (item.resource_name or "")[:60],
                    "subtitle": item.provider_used or "",
                    "url": "/infra",
                }
            )

        cicd_rows = session.exec(
            select(CICDPipeline)
            .where(sa_text("LOWER(tool_name) LIKE :t OR LOWER(COALESCE(prompt, '')) LIKE :t"))
            .order_by(CICDPipeline.timestamp.desc())
            .limit(5),
            params={"t": term},
        ).all()
        for item in cicd_rows:
            results.append(
                {
                    "type": "CI/CD",
                    "id": str(item.id or ""),
                    "title": item.tool_name or "",
                    "subtitle": (item.prompt or "")[:60],
                    "url": "/cicd",
                }
            )

    return results[:limit]


@router.post("/api/logs/scan-anomalies")
@limiter.limit("5/minute")
async def scan_anomalies(request: Request, current_user: User = Depends(get_current_user)):
    """Simulate a background log scan and create a predictive WARNING incident."""
    if not demo_data_enabled():
        return {
            "status": "no_data",
            "message": "Anomaly scanner requires demo mode or a real log source.",
        }

    from ..observability.metrics import record_demo_data_served

    record_demo_data_served("logs_scan_anomalies")
    await asyncio.sleep(3)

    record = save_incident(ANOMALY_INCIDENT)
    asyncio.create_task(
        _hitl_evaluate(
            record.id,
            ANOMALY_INCIDENT["severity"],
            {
                "action_plan": ANOMALY_INCIDENT["action_plan"],
                "commands": ANOMALY_INCIDENT["commands"],
            },
            ANOMALY_INCIDENT.get("owner_role", "Admin"),
            ANOMALY_INCIDENT.get("source", "anomaly-scanner"),
        )
    )

    create_notification(
        message="⚠️ Predictive anomaly detected: Gradual memory leak in auth-service (ETA to OOM: 4 h)",
        type="warning",
        incident_id=record.id,
    )

    return serialize_incident(record)


class QueryAnalyzeRequest(BaseModel):
    query: str
    database: str = "prod-postgres-primary"


_QUERY_ANALYZER_PROMPT = """You are a senior PostgreSQL and database performance expert.
Analyze the following SQL query and return ONLY a valid JSON object with these exact keys:
{
  "is_valid": true or false,
  "issues": ["list of problems found, or empty array"],
  "index_recommendations": ["list of CREATE INDEX suggestions based on SQL syntax alone, or empty array"],
  "estimated_cost": "a human-readable estimate like 'Low', 'Medium', 'High', or 'Very High' based on query shape only",
  "rewritten_query": "an optimized version of the query, or null if already optimal",
  "summary": "one sentence plain-English explanation of what the query does and its main performance concern"
}
Do NOT invent EXPLAIN ANALYZE output — live plans require a connected database.
Return ONLY the JSON. No markdown, no code fences, no explanation."""


@router.post("/api/db/analyze-query")
@limiter.limit("5/minute")
async def analyze_query(
    request: Request,
    req: QueryAnalyzeRequest,
    current_user: User = Depends(get_current_user),
):
    """AI-powered SQL query analysis: index recommendations and rewrite suggestions.

    Live EXPLAIN plans are not fabricated — connect a database for real EXPLAIN.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query cannot be empty.")

    prompt = f"Database: {req.database}\n\nSQL Query:\n{req.query}\n\n{_QUERY_ANALYZER_PROMPT}"

    try:
        raw = await ask_ai(prompt)
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        result = json.loads(cleaned)
    except Exception:
        result = {
            "is_valid": True,
            "issues": ["Could not parse AI response — showing fallback analysis."],
            "index_recommendations": [],
            "estimated_cost": "Unknown",
            "rewritten_query": None,
            "summary": "Unable to perform AI analysis. Please check your AI provider configuration.",
        }

    # Never return LLM-invented EXPLAIN output.
    result["explain_plan"] = None
    result["explain_note"] = (
        "Live EXPLAIN requires a connected database with query execution rights. "
        "Connect your database under Settings → Tool Registry → Database "
        "to enable real EXPLAIN ANALYZE output."
    )
    return result
