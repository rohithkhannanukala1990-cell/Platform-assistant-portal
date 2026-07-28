"""Alert noise agent — PagerDuty alert frequency analysis (rules-based)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


class AlertNoiseAgent(BaseAgent):
    name = "alert_noise_agent"
    description = "Alert noise analysis and deduplication recommendations."
    requires_approval_envs = []
    primary_tools = ["PagerDuty", "Datadog", "Grafana", "Prometheus"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        pd = await self._ground_pd(context, db)
        if pd is None:
            return self._no_data_result(
                context,
                "PagerDuty not connected. Connect a PagerDuty account in Tool Registry.",
                missing_tools=["PagerDuty"],
            )

        period_days = int(params.get("period_days") or 7)
        evidence: list[dict] = []

        try:
            incidents = await pd.list_incidents(
                status="triggered",
                limit=200,
                date_range="last_7_days",
            )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Failed to fetch PagerDuty incidents for noise analysis",
                details={"error": str(exc)[:300]},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        by_title: Counter = Counter()
        by_service: Counter = Counter()
        for inc in incidents:
            title = (inc.get("title") or "unknown").strip()
            by_title[title] += 1
            service = inc.get("service")
            if isinstance(service, dict):
                svc_name = service.get("summary") or service.get("name") or "unknown"
            else:
                svc_name = str(service or "unknown")
            by_service[svc_name] += 1
            evidence.append(
                self._evidence(
                    type="incident",
                    title=title[:200],
                    source="pagerduty",
                    url=inc.get("html_url"),
                    snippet=f"id={inc.get('id')} service={svc_name} status={inc.get('status')}",
                )
            )

        noisy_alerts = []
        suppression_candidates = []
        for title, count in by_title.most_common():
            per_day = count / max(period_days, 1)
            entry = {
                "title": title,
                "count": count,
                "per_day": round(per_day, 2),
                "method": "rules-based",
            }
            if per_day > 10:
                entry["noisy"] = True
                noisy_alerts.append(entry)
                suppression_candidates.append(title)
            elif count > 3:
                suppression_candidates.append(title)

        # Also surface service-level grouping as evidence of method.
        for svc, count in by_service.most_common(10):
            evidence.append(
                self._evidence(
                    type="group",
                    title=f"Service group: {svc}",
                    source="rules-based",
                    snippet=f"count={count} method=rules-based",
                )
            )

        return self._result(
            context,
            status="success",
            summary=f"{len(noisy_alerts)} noisy alert patterns in {len(incidents)} incidents",
            details={
                "total_alerts": len(incidents),
                "noisy_alerts": noisy_alerts,
                "suppression_candidates": suppression_candidates[:20],
                "analysis_period_days": period_days,
                "by_title": dict(by_title.most_common(20)),
                "by_service": dict(by_service.most_common(20)),
                "method": "rules-based",
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            },
            evidence=evidence[:80],
            grounding="live",
            confidence=0.85 if incidents else 0.7,
        )


alert_noise_agent = AlertNoiseAgent()
