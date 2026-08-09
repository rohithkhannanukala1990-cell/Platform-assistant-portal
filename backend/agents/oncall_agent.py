"""On-call agent — PagerDuty schedules, coverage gaps, HITL overrides."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def detect_coverage_gaps(
    schedule_layers: list[dict[str, Any]],
    *,
    window_start: datetime,
    window_end: datetime,
    schedule_id: str,
    schedule_name: str = "",
) -> list[dict[str, Any]]:
    """Find intervals in [window_start, window_end) with nobody on call.

    ``schedule_layers`` items: {user_id, start, end} covering on-call windows.
    """
    intervals: list[tuple[datetime, datetime]] = []
    for row in schedule_layers or []:
        s = _parse_dt(row.get("start") if isinstance(row, dict) else None)
        e = _parse_dt(row.get("end") if isinstance(row, dict) else None)
        if s and e and e > s:
            # Clip to window
            s = max(s, window_start)
            e = min(e, window_end)
            if e > s:
                intervals.append((s, e))
    intervals.sort(key=lambda x: x[0])

    gaps: list[dict[str, Any]] = []
    cursor = window_start
    for s, e in intervals:
        if s > cursor:
            gaps.append(
                {
                    "schedule_id": schedule_id,
                    "schedule": schedule_name or schedule_id,
                    "start": cursor.isoformat(),
                    "end": s.isoformat(),
                    "duration_hours": round((s - cursor).total_seconds() / 3600, 2),
                }
            )
        cursor = max(cursor, e)
    if cursor < window_end:
        gaps.append(
            {
                "schedule_id": schedule_id,
                "schedule": schedule_name or schedule_id,
                "start": cursor.isoformat(),
                "end": window_end.isoformat(),
                "duration_hours": round((window_end - cursor).total_seconds() / 3600, 2),
            }
        )
    return gaps


def fewest_oncall_hours(
    oncalls: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the user with the fewest on-call hours in the provided rows."""
    totals: dict[str, float] = {}
    names: dict[str, str] = {}
    for row in oncalls or []:
        uid = str(row.get("user_id") or row.get("user") or "")
        if not uid:
            continue
        names[uid] = str(row.get("user") or uid)
        s = _parse_dt(row.get("start"))
        e = _parse_dt(row.get("end"))
        hours = 0.0
        if s and e and e > s:
            hours = (e - s).total_seconds() / 3600
        totals[uid] = totals.get(uid, 0.0) + hours
    if not totals:
        return None
    best = min(totals.items(), key=lambda kv: kv[1])
    return {"user_id": best[0], "user": names.get(best[0], best[0]), "hours": round(best[1], 2)}


class OncallAgent(BaseAgent):
    name = "oncall_agent"
    description = "PagerDuty schedules, coverage gaps, and HITL overrides."
    requires_approval_envs = []
    primary_tools = ["PagerDuty"]
    read_only = False

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        action = (params.get("action") or params.get("task") or "detect_coverage_gaps").lower()
        if "override" in action:
            action = "propose_schedule_override"
        elif "escalation" in action:
            action = "propose_escalation_change"
        elif "gap_fill" in action or "fill" in action:
            action = "propose_gap_fill"
        elif "gap" in action or "coverage" in action:
            action = "detect_coverage_gaps"
        elif "oncall" in action or "current" in action:
            action = "get_current_oncall"

        pd = await self._ground_pd(context, db)
        if pd is None:
            return self._no_data_result(
                context,
                "PagerDuty not connected — add credentials in Settings → Tool Registry.",
                missing_tools=["PagerDuty"],
            )

        if action == "detect_coverage_gaps":
            return await self._detect_gaps(pd, params, context)
        if action == "propose_gap_fill":
            return await self._propose_gap_fill(pd, params, context)
        if action == "propose_schedule_override":
            return await self._propose_override(pd, params, context)
        if action == "propose_escalation_change":
            return await self._propose_escalation(pd, params, context)
        if action in {"get_current_oncall", "list_schedules"}:
            oncalls = await pd.get_current_oncall() if hasattr(pd, "get_current_oncall") else await pd.list_oncalls()
            schedules = []
            if hasattr(pd, "list_schedules"):
                schedules = await pd.list_schedules()
            return self._result(
                context,
                status="success",
                summary=f"{len(oncalls)} current on-call entries",
                details={"oncalls": oncalls, "schedules": schedules},
                grounding="live",
                confidence=0.85,
            )

        return self._result(
            context,
            status="success",
            summary=f"Unknown on-call action '{action}' — defaulting to coverage scan",
            details={},
            grounding="none",
            confidence=0.4,
        )

    async def _detect_gaps(self, pd, params: dict, context: PlatformContext) -> AgentResult:
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(days=int(params.get("days") or 30))
        # Injected gaps for tests
        if params.get("schedule_layers") is not None:
            schedule_id = params.get("schedule_id") or "SCHED1"
            gaps = detect_coverage_gaps(
                params["schedule_layers"],
                window_start=now if not params.get("window_start") else _parse_dt(params["window_start"]) or now,
                window_end=window_end if not params.get("window_end") else _parse_dt(params["window_end"]) or window_end,
                schedule_id=schedule_id,
                schedule_name=params.get("schedule_name") or schedule_id,
            )
        else:
            schedules = await pd.list_schedules()
            gaps = []
            for sched in schedules or []:
                sid = sched.get("id")
                if not sid:
                    continue
                detail = await pd.get_schedule_with_rotations(
                    sid, since=now.isoformat(), until=window_end.isoformat()
                )
                layers = detail.get("rendered_coverage") or detail.get("final_schedule") or []
                gaps.extend(
                    detect_coverage_gaps(
                        layers,
                        window_start=now,
                        window_end=window_end,
                        schedule_id=sid,
                        schedule_name=sched.get("name") or sid,
                    )
                )

        return self._result(
            context,
            status="success",
            summary=f"Found {len(gaps)} on-call coverage gap(s) in the next 30 days",
            details={"gaps": gaps, "action": "detect_coverage_gaps"},
            grounding="live",
            confidence=0.9,
            evidence=[
                self._evidence(
                    type="coverage_gap",
                    title=f"{g.get('schedule')} {g.get('start')}→{g.get('end')}",
                    source="pagerduty",
                    snippet=str(g),
                )
                for g in gaps[:20]
            ],
        )

    async def _propose_gap_fill(self, pd, params: dict, context: PlatformContext) -> AgentResult:
        gap = params.get("gap") or {}
        if not gap and params.get("schedule_layers") is not None:
            scan = await self._detect_gaps(pd, params, context)
            gaps = (scan.details or {}).get("gaps") or []
            gap = gaps[0] if gaps else {}
        if not gap:
            return self._no_data_result(
                context,
                "No coverage gap provided — run detect_coverage_gaps first.",
                missing_tools=["PagerDuty"],
            )

        recent = params.get("recent_oncalls")
        if recent is None:
            recent = await pd.list_oncalls(limit=100)
        suggestion = fewest_oncall_hours(recent) or {}
        user_id = params.get("user_id") or suggestion.get("user_id")
        if not user_id:
            return self._no_data_result(
                context,
                "No PagerDuty users available to fill the gap.",
                missing_tools=["PagerDuty"],
            )

        schedule_id = gap.get("schedule_id") or params.get("schedule_id")
        start = gap.get("start")
        end = gap.get("end")
        preview = {
            "type": "pagerduty_override",
            "action": "propose_gap_fill",
            "schedule_id": schedule_id,
            "user_id": user_id,
            "user": suggestion.get("user") or user_id,
            "start": start,
            "end": end,
            "suggested_because": "fewest_oncall_hours_last_30d",
            "suggested_hours": suggestion.get("hours"),
            "gap": gap,
        }
        return self._propose_artifact_result(
            context,
            connector="pagerduty",
            method="create_schedule_override",
            params={
                "schedule_id": schedule_id,
                "user_id": user_id,
                "start": start,
                "end": end,
            },
            preview=preview,
            grounding="live",
            summary=f"Fill coverage gap with {preview['user']} ({start} → {end})",
            details=preview,
        )

    async def _propose_override(self, pd, params: dict, context: PlatformContext) -> AgentResult:
        schedule_id = params.get("schedule_id")
        user_id = params.get("user_id")
        start = params.get("start")
        end = params.get("end")
        if not all([schedule_id, user_id, start, end]):
            return self._result(
                context,
                status="failed",
                summary="propose_schedule_override requires schedule_id, user_id, start, end",
                details={},
                grounding="none",
                confidence=0.0,
            )

        current = []
        if hasattr(pd, "get_current_oncall"):
            current = await pd.get_current_oncall(schedule_id=schedule_id)
        else:
            current = await pd.list_oncalls(schedule_id=schedule_id)

        preview = {
            "type": "pagerduty_override",
            "action": "propose_schedule_override",
            "schedule_id": schedule_id,
            "user_id": user_id,
            "start": start,
            "end": end,
            "currently_oncall": current,
            "after_override": {"user_id": user_id, "start": start, "end": end},
        }
        # HITL — create nothing before approval
        return self._propose_artifact_result(
            context,
            connector="pagerduty",
            method="create_schedule_override",
            params={
                "schedule_id": schedule_id,
                "user_id": user_id,
                "start": start,
                "end": end,
            },
            preview=preview,
            grounding="live",
            summary=f"Override schedule {schedule_id}: {user_id} ({start} → {end})",
            details=preview,
        )

    async def _propose_escalation(self, pd, params: dict, context: PlatformContext) -> AgentResult:
        policy_id = params.get("policy_id")
        rules = params.get("rules") or params.get("proposed_rules") or []
        if not policy_id or not rules:
            return self._result(
                context,
                status="failed",
                summary="propose_escalation_change requires policy_id and rules",
                details={},
                grounding="none",
                confidence=0.0,
            )
        current = {}
        if hasattr(pd, "list_escalation_policies"):
            policies = await pd.list_escalation_policies()
            current = next((p for p in policies if p.get("id") == policy_id), {})
        preview = {
            "type": "pagerduty_escalation",
            "policy_id": policy_id,
            "current_chain": current.get("rules") or current.get("escalation_rules") or [],
            "proposed_chain": rules,
        }
        return self._propose_artifact_result(
            context,
            connector="pagerduty",
            method="update_escalation_policy",
            params={"policy_id": policy_id, "rules": rules},
            preview=preview,
            grounding="live",
            summary=f"Update escalation policy {policy_id}",
            details=preview,
        )


oncall_agent = OncallAgent()
