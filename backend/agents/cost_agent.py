"""Cost agent — AWS Cost Explorer breakdown."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlmodel import Session

from ..connectors.aws_connector import AWSConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


class CostAgent(BaseAgent):
    name = "cost_agent"
    description = "Cloud cost breakdown and optimization recommendations."
    requires_approval_envs = []
    primary_tools = ["AWS", "GCP", "Azure"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session):
        today = date.today()
        start = params.get("start") or today.replace(day=1).isoformat()
        end = params.get("end") or today.isoformat()

        services: list = []
        try:
            services = await AWSConnector(_ACCOUNT).get_cost_explorer(start, end)
        except Exception:
            services = []

        amounts = []
        for row in services:
            try:
                amounts.append(float(row.get("amount") or 0))
            except (TypeError, ValueError):
                pass

        total_usd = round(sum(amounts), 2)
        sorted_svcs = sorted(services, key=lambda r: float(r.get("amount") or 0), reverse=True)
        top_5 = sorted_svcs[:5]

        days_elapsed = max(1, (today - today.replace(day=1)).days + 1)
        days_in_month = 30
        daily_avg = round(total_usd / days_elapsed, 2) if days_elapsed else 0.0
        projected_monthly = round(daily_avg * days_in_month, 2)

        trend = "stable"
        if len(amounts) >= 2:
            first_half = sum(amounts[: len(amounts) // 2]) if amounts else 0
            second_half = sum(amounts[len(amounts) // 2 :]) if amounts else 0
            if second_half > first_half * 1.1:
                trend = "increasing"
            elif second_half < first_half * 0.9:
                trend = "decreasing"

        return self._build_result(
            context,
            status="success",
            summary=f"Cloud spend ${total_usd:,.2f} ({start} → {end})",
            details={
                "total_usd": total_usd,
                "currency": "USD",
                "period": {"start": start, "end": end},
                "top_services": top_5,
                "projected_monthly": projected_monthly,
                "daily_avg": daily_avg,
                "trend": trend,
            },
            execution_log=f"Cost analysis at {datetime.now(timezone.utc).isoformat()}",
        )


cost_agent = CostAgent()
