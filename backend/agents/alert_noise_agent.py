"""Alert noise agent — PagerDuty alert frequency analysis."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlmodel import Session

from ..connectors.pagerduty_connector import PagerDutyConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


class AlertNoiseAgent(BaseAgent):
    name = "alert_noise_agent"
    description = "Alert noise analysis and deduplication recommendations."
    requires_approval_envs = []
    primary_tools = ["PagerDuty", "Datadog", "Grafana", "Prometheus"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        pd = PagerDutyConnector(_ACCOUNT)
        incidents: list = []
        period_days = 7

        try:
            incidents = await pd.list_incidents(
                status="triggered",
                limit=200,
                date_range="last_7_days",
            )
        except Exception:
            incidents = []

        by_title: Counter = Counter()
        for inc in incidents:
            title = (inc.get("title") or "unknown").strip()
            by_title[title] += 1

        noisy_alerts = []
        suppression_candidates = []
        for title, count in by_title.most_common():
            per_day = count / max(period_days, 1)
            entry = {"title": title, "count": count, "per_day": round(per_day, 2)}
            if per_day > 10:
                entry["noisy"] = True
                noisy_alerts.append(entry)
                suppression_candidates.append(title)
            elif count > 3:
                suppression_candidates.append(title)

        return self._build_result(
            context,
            status="success",
            summary=f"{len(noisy_alerts)} noisy alert patterns in {len(incidents)} incidents",
            details={
                "total_alerts": len(incidents),
                "noisy_alerts": noisy_alerts,
                "suppression_candidates": suppression_candidates[:20],
                "analysis_period_days": period_days,
                "by_title": dict(by_title.most_common(20)),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            },
        )


alert_noise_agent = AlertNoiseAgent()
