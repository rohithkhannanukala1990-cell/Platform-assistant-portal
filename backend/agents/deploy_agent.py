"""Deploy agent — Kubernetes rollouts with production HITL."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..connectors.kubernetes_connector import KubernetesConnector
from ..context import PlatformContext
from .base import BaseAgent

_ACCOUNT: dict = {}


def _parse_deploy_params(params: dict, task: str) -> tuple[str, str, str, str]:
    text = f"{params.get('task') or params.get('message') or task or ''} {params}"
    service = (
        params.get("service_name")
        or params.get("service")
        or _re_group(text, r"service[_\s-]*name[=:\s]+['\"]?([\w-]+)", r"deploy\s+([\w-]+)")
        or "app"
    )
    version = (
        params.get("version")
        or params.get("image_tag")
        or _re_group(text, r"version[=:\s]+([^\s,]+)", r"tag[=:\s]+([^\s,]+)", r"v?(\d+\.\d+\.\d+[-\w.]*)")
        or "latest"
    )
    target_env = (
        params.get("target_env")
        or params.get("environment")
        or _re_group(text, r"(production|prod|staging|dev|development)")
        or "development"
    ).lower()
    if target_env in ("prod", "dr"):
        target_env = "production"
    namespace = params.get("namespace") or ("production" if target_env == "production" else "default")
    return service, version, target_env, namespace


def _re_group(text: str, *patterns: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return None


class DeployAgent(BaseAgent):
    name = "deploy_agent"
    description = "Builds and applies deployment plans via CI/CD and Kubernetes."
    requires_approval_envs = ["production"]
    primary_tools = ["GitHub Actions", "ArgoCD", "Kubernetes", "Helm"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = str(params.get("task") or params.get("message") or "")
        service_name, version, target_env, namespace = _parse_deploy_params(params, task)
        image_tag = params.get("image") or f"{service_name}:{version}"
        env = target_env or (context.environment or "development").lower()

        details = {
            "service": service_name,
            "image_tag": image_tag,
            "namespace": namespace,
            "environment": env,
            "rolled_back": False,
        }

        if env in ("production", "prod", "dr") or context.is_production():
            return self._build_result(
                context,
                status="pending_approval",
                summary=f"Production deploy {service_name}:{version} requires approval",
                details=details,
                requires_approval=True,
                approval_payload={
                    "action": "deploy",
                    "service_name": service_name,
                    "image_tag": image_tag,
                    "namespace": namespace,
                    "environment": env,
                },
            )

        k8s = KubernetesConnector(_ACCOUNT)
        try:
            result = await k8s.deploy(service_name, image_tag, namespace)
            success = result.get("success", False)
            details["deploy_message"] = result.get("message", "")
            return self._build_result(
                context,
                status="success" if success else "failed",
                summary=result.get("message") or f"Deploy {service_name} → {image_tag}",
                details=details,
                execution_log=str(result),
            )
        except Exception as exc:
            return self._build_result(
                context,
                status="failed",
                summary=f"Deploy failed for {service_name}",
                details={**details, "error": str(exc)},
            )


deploy_agent = DeployAgent()
