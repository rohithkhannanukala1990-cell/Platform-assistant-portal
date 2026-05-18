"""Auto-heal agent — Kubernetes pod restarts for unhealthy workloads."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..connectors.kubernetes_connector import KubernetesConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


class AutoHealAgent(BaseAgent):
    name = "auto_heal_agent"
    description = "Low-risk automated healing for stale sessions, cache, and DB maintenance."
    requires_approval_envs = ["production"]
    primary_tools = ["Kubernetes", "ArgoCD"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        service_name = params.get("service_name") or "platform"
        namespace = params.get("namespace") or "default"
        pod_name = params.get("pod_name") or _extract_pod(task)
        k8s = KubernetesConnector(_ACCOUNT)

        pods_affected: list[str] = []
        actions: list[dict] = []

        try:
            pods = await k8s.list_pods(namespace)
            if pod_name:
                pods_affected = [pod_name]
            else:
                for p in pods:
                    if p.get("restarts", 0) >= 3 or p.get("status") not in ("Running", None):
                        pods_affected.append(p.get("name", ""))
                pods_affected = [p for p in pods_affected if p][:1]
                if not pods_affected and pods:
                    pods_affected = [pods[0].get("name", "")]
        except Exception:
            pods = []

        if context.is_production() and pods_affected:
            return self._build_result(
                context,
                status="pending_approval",
                summary=f"Auto-heal restart for {pods_affected} in {namespace} (production)",
                details={
                    "pods_affected": pods_affected,
                    "actions": [{"type": "restart_pod", "pod": p} for p in pods_affected],
                    "service_name": service_name,
                    "namespace": namespace,
                },
                requires_approval=True,
                approval_payload={
                    "action": "auto_heal",
                    "pods": pods_affected,
                    "namespace": namespace,
                    "params": params,
                },
            )

        execution_log: list[str] = []
        for pod in pods_affected:
            try:
                result = await k8s.restart_pod(pod, namespace)
                actions.append({"pod": pod, "result": result})
                execution_log.append(f"restart {pod}: {result}")
            except Exception as exc:
                actions.append({"pod": pod, "error": str(exc)})
                execution_log.append(f"restart {pod} failed: {exc}")

        success = any(a.get("result", {}).get("success") for a in actions if "result" in a)
        return self._build_result(
            context,
            status="success" if success else "failed",
            summary=f"Auto-heal completed for {service_name} ({len(pods_affected)} pod(s))",
            details={
                "pods_affected": pods_affected,
                "actions": actions,
                "execution_log": execution_log,
                "service_name": service_name,
                "namespace": namespace,
            },
            execution_log="\n".join(execution_log),
        )


def _extract_pod(text: str) -> str | None:
    m = re.search(r"pod[/\s-]+([\w.-]+)", text, re.I)
    return m.group(1) if m else None


auto_heal_agent = AutoHealAgent()
