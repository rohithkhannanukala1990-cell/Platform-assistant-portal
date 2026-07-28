"""Alert noise agent — rules-based correlation and PagerDuty frequency analysis (Phase G4)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlmodel import Session

from ..context import PlatformContext
from ..services.alert_rules import list_alert_rules
from .base import AgentResult, BaseAgent

CORRELATION_LABEL = "Rules-based correlation"


class AlertNoiseAgent(BaseAgent):
    name = "alert_noise_agent"
    description = "Rules-based alert correlation and noise analysis (not ML)."
    requires_approval_envs = []
    primary_tools = ["PagerDuty", "Datadog", "Grafana", "Prometheus"]
    read_only = True

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        tenant_id = context.tenant_id or "default"
        configured_rules = list_alert_rules(tenant_id)
        rules_summary = [
            {
                "id": r["id"],
                "name": r["name"],
                "action": r["action"],
                "group_window_sec": r["group_window_sec"],
                "enabled": r["enabled"],
            }
            for r in configured_rules
            if r.get("enabled")
        ]

        pd = await self._ground_pd(context, db)
        if pd is None and not configured_rules:
            return self._no_data_result(
                context,
                "PagerDuty not connected. Connect a PagerDuty account in Tool Registry.",
                missing_tools=["PagerDuty"],
            )

        period_days = int(params.get("period_days") or 7)
        evidence: list[dict] = []
        incidents: list[dict] = []

        if pd is not None:
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
                    summary=f"{CORRELATION_LABEL}: failed to fetch PagerDuty incidents",
                    details={"error": str(exc)[:300], "correlation_label": CORRELATION_LABEL},
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
                "method": CORRELATION_LABEL,
            }
            if per_day > 10:
                entry["noisy"] = True
                noisy_alerts.append(entry)
                suppression_candidates.append(title)
            elif count > 3:
                suppression_candidates.append(title)

        for rule in rules_summary[:15]:
            evidence.append(
                self._evidence(
                    type="rule",
                    title=rule["name"],
                    source="alert_rules",
                    snippet=f"action={rule['action']} window={rule['group_window_sec']}s",
                )
            )

        for svc, count in by_service.most_common(10):
            evidence.append(
                self._evidence(
                    type="group",
                    title=f"Service group: {svc}",
                    source=CORRELATION_LABEL,
                    snippet=f"count={count} method={CORRELATION_LABEL}",
                )
            )

        return self._result(
            context,
            status="success",
            summary=(
                f"{CORRELATION_LABEL}: {len(noisy_alerts)} noisy patterns in "
                f"{len(incidents)} incidents; {len(rules_summary)} active rules"
            ),
            details={
                "correlation_label": CORRELATION_LABEL,
                "configured_rules": len(rules_summary),
                "rules": rules_summary,
                "total_alerts": len(incidents),
                "noisy_alerts": noisy_alerts,
                "suppression_candidates": suppression_candidates[:20],
                "analysis_period_days": period_days,
                "by_title": dict(by_title.most_common(20)),
                "by_service": dict(by_service.most_common(20)),
                "method": CORRELATION_LABEL,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            },
            evidence=evidence[:80],
            grounding="live" if incidents else ("rules" if rules_summary else "none"),
            confidence=0.85 if incidents or rules_summary else 0.7,
        )


alert_noise_agent = AlertNoiseAgent()
