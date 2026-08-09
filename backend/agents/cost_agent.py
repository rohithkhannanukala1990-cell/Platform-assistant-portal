"""Cost agent — AWS Cost Explorer breakdown (no fantasy $0.00)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


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

        conn = await self._ground_aws(context, db)
        if conn is None:
            return self._no_data_result(
                context,
                "AWS not connected — add AWS credentials in Tool Registry "
                "under Settings → Tool Registry → AWS.",
                missing_tools=["AWS"],
            )

        try:
            services = await conn.get_cost_explorer(start, end)
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

        if bool(params.get("propose", True)) and top_5:
            jira = await self._ground_jira(context, db)
            if jira is None:
                return self._no_data_result(
                    context,
                    "Jira not connected — cannot propose cost rightsizing issues. "
                    "Add Jira in Settings → Tool Registry.",
                    missing_tools=["Jira"],
                )
            saving = round(projected_monthly * 0.15, 2)
            lines = "\n".join(
                f"- {r.get('service')}: ${float(r.get('amount') or 0):,.2f}"
                for r in top_5
            )
            summary_line = f"Rightsizing opportunities (~${saving:,.2f}/mo projected saving)"
            description = (
                f"Period {start} → {end}\nProjected monthly: ${projected_monthly:,.2f}\n"
                f"Estimated saving: ${saving:,.2f}/mo\n\nTop services:\n{lines}"
            )
            project_key = params.get("project_key") or "FINOPS"
            return self._propose_artifact_result(
                context,
                connector="jira",
                method="create_issue",
                params={
                    "project_key": project_key,
                    "summary": summary_line,
                    "description": description,
                    "issue_type": "Task",
                    "priority": "Medium",
                    "labels": ["cost", "rightsizing"],
                },
                preview={
                    "type": "jira_issue",
                    "project_key": project_key,
                    "summary": summary_line,
                    "description": description[:4000],
                    "projected_monthly_saving": saving,
                },
                grounding="live",
                summary=f"Propose Jira issue: {summary_line}",
                details={
                    "total_usd": total_usd,
                    "projected_monthly": projected_monthly,
                    "top_services": top_5,
                    "trend": trend,
                },
                evidence=evidence[:50],
            )

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
