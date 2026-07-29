"""Deploy agent — Kubernetes rollouts with dry-run plan and production HITL."""

from __future__ import annotations

import json
import re

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


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

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        task = str(params.get("task") or params.get("message") or "")
        service_name, version, target_env, namespace = _parse_deploy_params(params, task)
        image_tag = params.get("image") or f"{service_name}:{version}"
        env = target_env or (context.environment or "development").lower()
        dry_run = params.get("dry_run", True)
        if isinstance(dry_run, str):
            dry_run = dry_run.lower() not in ("false", "0", "no")

        evidence: list[dict] = []
        k8s = await self._ground_k8s(context, db)
        grounding = "none"

        if k8s is not None:
            grounding = "live"
            try:
                pods = await k8s.list_pods(namespace)
                evidence.append(
                    self._evidence(
                        type="k8s_namespace",
                        title=f"Namespace {namespace}",
                        source="kubernetes",
                        snippet=f"pod_count={len(pods)}",
                    )
                )
                for pod in pods[:15]:
                    if service_name in str(pod.get("name") or ""):
                        evidence.append(
                            self._evidence(
                                type="k8s_pod",
                                title=str(pod.get("name")),
                                source="kubernetes",
                                snippet=json.dumps(pod, default=str)[:600],
                            )
                        )
            except Exception as exc:
                grounding = "partial"
                evidence.append(
                    self._evidence(
                        type="error",
                        title="k8s list_pods failed",
                        source="kubernetes",
                        snippet=str(exc)[:300],
                    )
                )
        else:
            grounding = "partial"
            evidence.append(
                self._evidence(
                    type="plan",
                    title="Deploy plan without live k8s inventory",
                    source="platform",
                    snippet="Kubernetes connector unavailable; plan is dry-run only",
                )
            )

        evidence.append(
            self._evidence(
                type="deploy_plan",
                title=f"Deploy {service_name} → {image_tag}",
                source="deploy_agent",
                snippet=json.dumps(
                    {
                        "service": service_name,
                        "image_tag": image_tag,
                        "namespace": namespace,
                        "environment": env,
                        "dry_run": dry_run,
                    },
                    default=str,
                ),
            )
        )

        commands = [
            f"kubectl set image deployment/{service_name} "
            f"{service_name}={image_tag} -n {namespace}",
            f"kubectl rollout status deployment/{service_name} -n {namespace}",
        ]

        details = {
            "service": service_name,
            "image_tag": image_tag,
            "namespace": namespace,
            "environment": env,
            "rolled_back": False,
            "dry_run": dry_run,
        }

        # Always treat production as HITL via finalize; dry_run stays plan-only.
        if dry_run or env in ("production", "prod", "dr") or context.is_production():
            return self._finalize_with_policy(
                context,
                summary=(
                    f"{'Dry-run plan' if dry_run else 'Production deploy'} "
                    f"{service_name}:{version} → {namespace}"
                ),
                details=details,
                commands=commands,
                evidence=evidence,
                grounding=grounding,
                confidence=0.7 if grounding == "live" else 0.5,
                task=f"deploy {service_name}",
                recommended_actions=[
                    {
                        "title": f"Apply deploy {service_name}:{version}",
                        "risk": "high" if env == "production" else "medium",
                        "requires_approval": True,
                    }
                ],
            )

        # Non-prod, dry_run=False: still route through policy (never unvalidated).
        return self._finalize_with_policy(
            context,
            summary=f"Deploy {service_name} → {image_tag}",
            details=details,
            commands=commands,
            evidence=evidence,
            grounding=grounding,
            confidence=0.7 if grounding == "live" else 0.5,
            task=f"deploy {service_name}",
        )


deploy_agent = DeployAgent()
