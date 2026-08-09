"""Cost agent — Cost Explorer plus HITL rightsizing (direct AWS or terraform PR)."""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent

# Simple downsample map for common families
_DOWNSIZE = {
    "m5.4xlarge": "m5.2xlarge",
    "m5.2xlarge": "m5.xlarge",
    "m5.xlarge": "m5.large",
    "m5.large": "m5.large",
    "t3.2xlarge": "t3.xlarge",
    "t3.xlarge": "t3.large",
    "t3.large": "t3.medium",
    "t3.medium": "t3.small",
    "r5.2xlarge": "r5.xlarge",
    "r5.xlarge": "r5.large",
    "c5.2xlarge": "c5.xlarge",
    "c5.xlarge": "c5.large",
    "db.m5.2xlarge": "db.m5.xlarge",
    "db.m5.xlarge": "db.m5.large",
    "db.r5.2xlarge": "db.r5.xlarge",
}


def _cost_remediation_mode(params: dict) -> str:
    mode = (
        params.get("COST_REMEDIATION_MODE")
        or params.get("cost_remediation_mode")
        or os.getenv("COST_REMEDIATION_MODE")
        or ""
    ).strip().lower()
    if not mode:
        try:
            from ..db.repositories.settings import get_settings

            settings = get_settings() or {}
            mode = str(settings.get("COST_REMEDIATION_MODE") or "").strip().lower()
        except Exception:
            mode = ""
    if mode not in {"direct", "terraform_pr"}:
        mode = "terraform_pr"
    return mode


def _monthly_cost_estimate(instance_type: str) -> float:
    # Rough placeholders for proposal math (tests inject costs)
    table = {
        "m5.4xlarge": 560.0,
        "m5.2xlarge": 280.0,
        "m5.xlarge": 140.0,
        "m5.large": 70.0,
        "t3.2xlarge": 240.0,
        "t3.xlarge": 120.0,
        "t3.large": 60.0,
        "t3.medium": 30.0,
        "t3.small": 15.0,
    }
    return float(table.get(instance_type, 100.0))


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
        allow_production = bool(params.get("allow_production"))

        conn = await self._ground_aws(context, db)
        if conn is None:
            return self._no_data_result(
                context,
                "AWS not connected — add AWS credentials in Tool Registry "
                "under Settings → Tool Registry → AWS.",
                missing_tools=["AWS"],
            )

        # Rightsizing path when requested or when instances provided
        if params.get("rightsize") or params.get("instances") is not None:
            return await self._rightsizing_propose(
                params, context, db, conn, allow_production=allow_production
            )

        try:
            services = await conn.get_cost_explorer(start, end)
        except Exception as exc:
            return self._no_data_result(
                context,
                f"AWS Cost Explorer failed: {str(exc)[:200]}. Connect AWS and retry.",
                missing_tools=["AWS"],
            )

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

        # Default propose path: try rightsizing from live instances first
        if bool(params.get("propose", True)):
            rs = await self._rightsizing_propose(
                {**params, "rightsize": True},
                context,
                db,
                conn,
                allow_production=allow_production,
                soft_fail=True,
            )
            if rs is not None and rs.status == "pending_approval":
                return rs

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

    async def _rightsizing_propose(
        self,
        params: dict,
        context: PlatformContext,
        db: Session,
        conn,
        *,
        allow_production: bool,
        soft_fail: bool = False,
    ) -> AgentResult | None:
        mode = _cost_remediation_mode(params)
        instances = params.get("instances")
        if instances is None:
            try:
                instances = await conn.list_instances(params.get("region"))
            except Exception:
                instances = []
        if not instances:
            if soft_fail:
                return None
            return self._no_data_result(
                context,
                "No EC2 instances available for rightsizing analysis.",
                missing_tools=["AWS"],
            )

        candidates = []
        skipped = []
        for inst in instances:
            tags = inst.get("tags") or {}
            # Normalize tag dict from list form
            if isinstance(tags, list):
                tags = {t.get("Key"): t.get("Value") for t in tags if isinstance(t, dict)}
            tag_l = {str(k).lower(): str(v).lower() for k, v in tags.items()}
            if "do-not-resize" in tag_l or tag_l.get("do-not-resize") in {"true", "1", "yes"}:
                skipped.append({"id": inst.get("id"), "reason": "do-not-resize"})
                continue
            if tag_l.get("environment") == "production" and not allow_production:
                skipped.append({"id": inst.get("id"), "reason": "production"})
                continue

            util = inst.get("utilization")
            if util is None and hasattr(conn, "get_instance_utilization"):
                try:
                    util = await conn.get_instance_utilization(
                        inst["id"], days=14, region=params.get("region")
                    )
                except Exception:
                    util = None
            util = util or {}
            cpu = util.get("cpu") or {}
            p95 = cpu.get("p95_approx")
            if p95 is None and params.get("force_candidate"):
                p95 = 10.0
            if p95 is None or float(p95) >= 20.0:
                skipped.append({"id": inst.get("id"), "reason": f"p95_cpu={p95}"})
                continue

            current_type = str(inst.get("type") or inst.get("instance_type") or "")
            proposed_type = (
                params.get("proposed_type")
                or _DOWNSIZE.get(current_type)
                or current_type
            )
            if proposed_type == current_type and not params.get("proposed_type"):
                skipped.append({"id": inst.get("id"), "reason": "no_smaller_type"})
                continue
            current_cost = float(
                inst.get("current_monthly_cost") or _monthly_cost_estimate(current_type)
            )
            projected_cost = float(
                inst.get("projected_monthly_cost") or _monthly_cost_estimate(proposed_type)
            )
            saving = round(current_cost - projected_cost, 2)
            candidates.append(
                {
                    "instance_id": inst.get("id"),
                    "current_type": current_type,
                    "proposed_type": proposed_type,
                    "current_monthly_cost": current_cost,
                    "projected_monthly_cost": projected_cost,
                    "projected_monthly_saving": saving,
                    "utilization": util,
                }
            )

        if not candidates:
            if soft_fail:
                return None
            return self._result(
                context,
                status="success",
                summary="No rightsizing candidates (CPU p95>=20%, tagged, or production)",
                details={"skipped": skipped},
                grounding="live",
                confidence=0.7,
            )

        pick = candidates[0]
        preview = {
            "type": "cost_rightsizing",
            "mode": mode,
            **pick,
            "candidates": candidates,
            "skipped": skipped,
        }

        if mode == "direct":
            return self._propose_artifact_result(
                context,
                connector="aws",
                method="modify_instance_type",
                params={
                    "instance_id": pick["instance_id"],
                    "instance_type": pick["proposed_type"],
                    "region": params.get("region"),
                },
                preview=preview,
                grounding="live",
                summary=(
                    f"Rightsize {pick['instance_id']}: "
                    f"{pick['current_type']} → {pick['proposed_type']} "
                    f"(~${pick['projected_monthly_saving']}/mo)"
                ),
                details=preview,
            )

        # terraform_pr (default)
        github = await self._ground_github(context, db)
        if github is None:
            return self._no_data_result(
                context,
                "GitHub not connected — terraform_pr rightsizing requires GitHub. "
                "Or set COST_REMEDIATION_MODE=direct.",
                missing_tools=["GitHub"],
                details=preview,
            )
        repo = params.get("repo") or "infra/terraform"
        path = params.get("tf_path") or params.get("path") or "ec2.tf"
        content = (
            params.get("tf_content")
            or (
                f'# Rightsizing proposal for {pick["instance_id"]}\n'
                f'resource "aws_instance" "target" {{\n'
                f'  instance_type = "{pick["proposed_type"]}"\n'
                f"}}\n"
            )
        )
        return self._propose_artifact_result(
            context,
            connector="github",
            method="cost_rightsizing_pr",
            params={
                "repo": repo,
                "path": path,
                "content": content,
                "branch_name": f"finops/rightsize-{pick['instance_id']}",
                "base": params.get("base") or "main",
                "title": (
                    f"Rightsize {pick['instance_id']} "
                    f"{pick['current_type']}→{pick['proposed_type']}"
                ),
                "body": (
                    f"Projected saving ${pick['projected_monthly_saving']}/mo\n\n"
                    f"Utilisation: {pick.get('utilization')}"
                ),
            },
            preview=preview,
            grounding="live",
            summary=(
                f"Open Terraform PR to rightsize {pick['instance_id']} "
                f"({pick['current_type']} → {pick['proposed_type']})"
            ),
            details=preview,
        )


cost_agent = CostAgent()
