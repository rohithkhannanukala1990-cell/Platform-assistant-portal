"""Compliance agent — SOC2 evidence collection and gap scans (HITL evidence pack)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _resolve_period(params: dict) -> tuple[datetime, datetime]:
    end = _parse_dt(params.get("period_end")) or datetime.now(timezone.utc)
    start = _parse_dt(params.get("period_start"))
    if start is None:
        days = int(params.get("days") or 90)
        start = end - timedelta(days=days)
    return start, end


class ComplianceAgent(BaseAgent):
    name = "compliance_agent"
    description = "SOC2 evidence collection and gap detection across the portal."
    primary_tools = ["platform"]
    read_only = False

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        action = (params.get("action") or "scan_gaps").lower()
        if action in {"collect", "collect_evidence"}:
            return self._collect(params, context)
        if action in {"scan_gaps", "gaps"}:
            return self._scan(params, context)
        if action in {"generate_evidence_pack", "generate_pack", "pack"}:
            return self._propose_pack(params, context)
        return self._scan(params, context)

    def _collect(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..services.compliance_service import (
            CONTROLS,
            collect_all_controls,
            collect_evidence,
            persist_evidence_run,
        )

        start, end = _resolve_period(params)
        cid = str(params.get("control_id") or "").strip()
        if cid:
            res = collect_evidence(
                control_id=cid,
                tenant_id=context.tenant_id or "default",
                period_start=start,
                period_end=end,
            )
            persist_evidence_run(
                tenant_id=context.tenant_id or "default",
                control_results={cid: res},
                period_start=start,
                period_end=end,
                collected_by=context.user_id or "system",
            )
            return self._result(
                context,
                status="success",
                summary=(
                    f"Collected {len(res.get('evidence') or [])} evidence rows "
                    f"and {len(res.get('gaps') or [])} gap(s) for {cid}"
                ),
                details={
                    "control_id": cid,
                    "control_name": CONTROLS.get(cid, {}).get("name", ""),
                    "evidence": res.get("evidence") or [],
                    "gaps": res.get("gaps") or [],
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                },
                grounding="live",
                confidence=0.85,
            )
        results = collect_all_controls(
            tenant_id=context.tenant_id or "default",
            period_start=start,
            period_end=end,
        )
        persist_evidence_run(
            tenant_id=context.tenant_id or "default",
            control_results=results,
            period_start=start,
            period_end=end,
            collected_by=context.user_id or "system",
        )
        summary = {
            cid: {
                "evidence_count": len(r.get("evidence") or []),
                "gap_count": len(r.get("gaps") or []),
            }
            for cid, r in results.items()
        }
        total_gaps = sum(s["gap_count"] for s in summary.values())
        return self._result(
            context,
            status="success",
            summary=f"Collected evidence for {len(results)} controls; {total_gaps} gap(s)",
            details={
                "controls": results,
                "summary": summary,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            },
            grounding="live",
            confidence=0.85,
        )

    def _scan(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..services.compliance_service import scan_gaps

        start, end = _resolve_period(params)
        gaps = scan_gaps(
            tenant_id=context.tenant_id or "default",
            period_start=start,
            period_end=end,
        )
        return self._result(
            context,
            status="success",
            summary=f"Detected {len(gaps)} compliance gap(s) across mapped controls",
            details={
                "gaps": gaps,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
            },
            grounding="live",
            confidence=0.85,
            evidence=[
                self._evidence(
                    type="gap",
                    title=str(g.get("control")) + ": " + str(g.get("type")),
                    source="compliance_agent",
                    snippet=json.dumps(g, default=str),
                )
                for g in gaps[:20]
            ],
        )

    def _propose_pack(self, params: dict, context: PlatformContext) -> AgentResult:
        from ..services.compliance_service import (
            CONTROLS,
            build_evidence_pack,
        )

        start, end = _resolve_period(params)
        # Preview only — do not persist bytes to the DB. Byte payload is emitted
        # on approval via the compliance connector path in artifact_service.
        summary_map = {
            cid: CONTROLS[cid]["name"] for cid in CONTROLS
        }
        # NOTE: we generate a preview-summary pack (evidence *counts*) at
        # propose-time, but the actual pack bytes are re-generated on approval
        # from the DB-frozen period so nothing sensitive is stored twice.
        from .base import BaseAgent  # noqa: F401 — for typing clarity

        preview = {
            "type": "compliance_evidence_pack",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "controls": summary_map,
            "note": (
                "Approval will generate a ZIP containing per-control JSON "
                "and a summary manifest. Distribution outside the portal is "
                "considered sensitive."
            ),
        }
        params_frozen = {
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "controls": list(CONTROLS.keys()),
        }
        return self._propose_artifact_result(
            context,
            connector="compliance",
            method="generate_evidence_pack",
            params=params_frozen,
            preview=preview,
            grounding="live",
            summary=f"Propose evidence pack ({start.date()} → {end.date()})",
            details={
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "controls": list(CONTROLS.keys()),
            },
        )


compliance_agent = ComplianceAgent()
