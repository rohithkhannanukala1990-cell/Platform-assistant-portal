"""Auto-heal agent — Kubernetes pod restarts from observed evidence only."""

from __future__ import annotations

import json
import re

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


def _extract_pod(text: str) -> str | None:
    m = re.search(r"pod[/\s-]+([\w.-]+)", text, re.I)
    return m.group(1) if m else None


class AutoHealAgent(BaseAgent):
    name = "auto_heal_agent"
    description = "Low-risk automated healing for stale sessions, cache, and DB maintenance."
    requires_approval_envs = ["production"]
    primary_tools = ["Kubernetes", "ArgoCD"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        task = str(params.get("task") or params.get("message") or "")
        service_name = params.get("service_name")
        namespace = params.get("namespace") or "default"
        pod_name = params.get("pod_name") or _extract_pod(task)
        k8s = await self._ground_k8s(context, db)
        if k8s is None:
            return self._no_data_result(
                context,
                "Kubernetes not connected. Connect a Kubernetes account in Tool Registry.",
                missing_tools=["Kubernetes"],
                details={
                    "pods_affected": [],
                    "actions": [],
                    "service_name": service_name,
                    "namespace": namespace,
                },
            )

        evidence: list[dict] = []
        pods_affected: list[str] = []
        try:
            pods = await k8s.list_pods(namespace)
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary=f"Failed to list pods in {namespace}",
                details={
                    "pods_affected": [],
                    "actions": [],
                    "service_name": service_name,
                    "namespace": namespace,
                    "error": str(exc)[:300],
                },
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        for p in pods:
            evidence.append(
                self._evidence(
                    type="k8s_pod",
                    title=str(p.get("name") or "pod"),
                    source="kubernetes",
                    snippet=json.dumps(
                        {
                            "name": p.get("name"),
                            "status": p.get("status"),
                            "restarts": p.get("restarts"),
                            "namespace": namespace,
                        },
                        default=str,
                    )[:800],
                )
            )

        if not evidence:
            return self._no_data_result(
                context,
                f"No pods observed in namespace {namespace}; cannot propose auto-heal.",
                missing_tools=["Kubernetes"],
                details={"namespace": namespace, "service_name": service_name},
            )

        if pod_name:
            # Only heal if the named pod appears in live evidence (or explicitly requested
            # and present); do not invent pods.
            names = {str(p.get("name") or "") for p in pods}
            if pod_name in names:
                pods_affected = [pod_name]
            else:
                return self._result(
                    context,
                    status="failed",
                    summary=f"Pod {pod_name} not found in namespace {namespace}",
                    details={
                        "pods_affected": [],
                        "actions": [],
                        "service_name": service_name,
                        "namespace": namespace,
                    },
                    evidence=evidence,
                    grounding="live",
                    confidence=0.9,
                    errors=["pod_not_found"],
                )
        else:
            for p in pods:
                restarts = p.get("restarts", 0) or 0
                status = p.get("status")
                if restarts >= 3 or (status and status not in ("Running", "Succeeded")):
                    name = p.get("name") or ""
                    if name:
                        pods_affected.append(name)
            pods_affected = pods_affected[:3]

        if not pods_affected:
            return self._result(
                context,
                status="success",
                summary=f"No unhealthy pods observed in {namespace}; no heal actions proposed",
                details={
                    "pods_affected": [],
                    "actions": [],
                    "service_name": service_name,
                    "namespace": namespace,
                    "pod_count": len(pods),
                },
                evidence=evidence,
                grounding="live",
                confidence=0.85,
            )

        commands = [
            f"kubectl delete pod/{pod} -n {namespace}" for pod in pods_affected
        ]
        details = {
            "pods_affected": pods_affected,
            "actions": [{"type": "restart_pod", "pod": p} for p in pods_affected],
            "service_name": service_name,
            "namespace": namespace,
        }
        return self._finalize_with_policy(
            context,
            summary=f"Auto-heal restart plan for {pods_affected} in {namespace}",
            details=details,
            commands=commands,
            evidence=evidence,
            grounding="live",
            confidence=0.8,
            task=task[:200] or "auto_heal",
            recommended_actions=[
                {
                    "title": f"Restart pod {p}",
                    "risk": "medium",
                    "requires_approval": self._should_require_approval(context),
                }
                for p in pods_affected
            ],
        )


auto_heal_agent = AutoHealAgent()
