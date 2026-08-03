"""Cost agent — AWS Cost Explorer breakdown (no fantasy $0.00)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from sqlmodel import Session

from ..connectors.aws_connector import AWSConnector
from ..context import PlatformContext
from ..services.aws_access import try_aws_connector_from_context
from .base import AgentResult, BaseAgent

_ACCOUNT: dict = {}


def _aws_configured(context: PlatformContext) -> bool:
    if context.tool_accounts.get("aws"):
        return True
    return bool(
        (os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
        or (os.getenv("AWS_PROFILE") or "").strip()
        or (os.getenv("AWS_ROLE_ARN") or "").strip()
    )


class CostAgent(BaseAgent):
    name = "cost_agent"
    description = "Cloud cost breakdown and optimization recommendations."
    requires_approval_envs = []
    primary_tools = ["AWS", "GCP", "Azure"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        today = date.today()
        start = params.get("start") or today.replace(day=1).isoformat()
        end = params.get("end") or today.isoformat()

        if not _aws_configured(context):
            return self._no_data_result(
                context,
                "AWS not connected. Connect AWS Cost Explorer credentials before cost analysis.",
                missing_tools=["AWS"],
            )

        try:
            services = await (try_aws_connector_from_context(context, db=db) or AWSConnector(_ACCOUNT)).get_cost_explorer(start, end)
        except Exception as exc:
            return self._no_data_result(
                context,
                f"AWS Cost Explorer failed: {str(exc)[:200]}. Connect AWS and retry.",
                missing_tools=["AWS"],
            )

        # Connector returns [] on auth/API failure — do not report $0.00 success.
        if not services:
            return self._no_data_result(
                context,
                "AWS Cost Explorer returned no data. Connect AWS / verify Cost Explorer access.",
                missing_tools=["AWS"],
                details={"period": {"start": start, "end": end}},
            )

        evidence = []
        amounts = []
        for row in services:
            try:
                amounts.append(float(row.get("amount") or 0))
            except (TypeError, ValueError):
                pass
            evidence.append(
                self._evidence(
                    type="cost_row",
                    title=str(row.get("service") or "service"),
                    source="aws_cost_explorer",
                    snippet=f"amount={row.get('amount')} {row.get('unit') or 'USD'}",
                )
            )

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

        return self._result(
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
            evidence=evidence[:50],
            grounding="live",
            confidence=0.85,
            execution_log=f"Cost analysis at {datetime.now(timezone.utc).isoformat()}",
        )


cost_agent = CostAgent()
