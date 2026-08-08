"""Infra agent — EC2, pods, and nodes inventory (grounded)."""

from __future__ import annotations

import json
import re

from sqlmodel import Session

from ..context import PlatformContext
from .base import AgentResult, BaseAgent


class InfraAgent(BaseAgent):
    name = "infra_agent"
    description = "Terraform/Pulumi infrastructure changes across cloud providers."
    requires_approval_envs = ["production"]
    primary_tools = ["Terraform", "Pulumi", "AWS", "GCP", "Azure", "Kubernetes"]

    async def run(self, params: dict, context: PlatformContext, db: Session) -> AgentResult:
        params = params if isinstance(params, dict) else {}
        task = (params.get("task") or params.get("message") or "").lower()
        namespace = params.get("namespace") or "default"
        region = params.get("region")
        env = (context.environment or "development").lower()

        wants_k8s = bool(
            re.search(r"\bpod|pods|node|nodes|scale|delete|k8s|kubernetes\b", task)
            or not re.search(r"\bec2|instance|aws\b", task)
        )
        wants_aws = bool(re.search(r"\bec2|instance|aws\b", task))
        wants_mutate = bool(re.search(r"\bscale|delete|destroy|terminate\b", task))

        k8s = await self._ground_k8s(context, db) if wants_k8s else None
        aws = await self._ground_aws(context, db) if wants_aws or not wants_k8s else None

        if wants_k8s and k8s is None and not wants_aws:
            return self._no_data_result(
                context,
                "Kubernetes not connected. Connect a Kubernetes account in Tool Registry.",
                missing_tools=["Kubernetes"],
                details={
                    "resource_type": "pods",
                    "count": 0,
                    "items": [],
                    "environment": env,
                },
            )

        if wants_aws and not wants_k8s and aws is None:
            return self._no_data_result(
                context,
                "AWS not connected — add AWS credentials in Tool Registry "
                "under Settings → Tool Registry → AWS to inspect EC2 instances.",
                missing_tools=["AWS"],
                details={"resource_type": "ec2", "count": 0, "items": [], "environment": env},
            )

        resource_type = "mixed"
        items: list | dict = []
        evidence: list[dict] = []
        grounding = "none"
        aws_ok = False
        k8s_ok = False
        errors: list[str] = []

        try:
            if re.search(r"\bec2|instance|aws\b", task) and not re.search(
                r"\bpod|pods|node|nodes\b", task
            ):
                if aws is None:
                    return self._no_data_result(
                        context,
                        "AWS not connected — add AWS credentials in Tool Registry "
                        "under Settings → Tool Registry → AWS to inspect EC2 instances.",
                        missing_tools=["AWS"],
                    )
                resource_type = "ec2"
                items = await aws.list_instances(region)
                aws_ok = True
                grounding = "live"
                for inst in (items or [])[:30]:
                    evidence.append(
                        self._evidence(
                            type="ec2_instance",
                            title=str(inst.get("name_tag") or inst.get("id") or "instance"),
                            source="aws",
                            snippet=json.dumps(inst, default=str)[:800],
                        )
                    )
            elif re.search(r"\bpod|pods\b", task):
                if k8s is None:
                    return self._no_data_result(
                        context,
                        "Kubernetes not connected.",
                        missing_tools=["Kubernetes"],
                    )
                resource_type = "pods"
                items = await k8s.list_pods(namespace)
                k8s_ok = True
                grounding = "live"
                for pod in (items or [])[:40]:
                    evidence.append(
                        self._evidence(
                            type="k8s_pod",
                            title=str(pod.get("name") or "pod"),
                            source="kubernetes",
                            snippet=json.dumps(pod, default=str)[:800],
                        )
                    )
            elif re.search(r"\bnode|nodes\b", task):
                if k8s is None:
                    return self._no_data_result(
                        context,
                        "Kubernetes not connected.",
                        missing_tools=["Kubernetes"],
                    )
                resource_type = "nodes"
                items = await k8s.list_nodes()
                k8s_ok = True
                grounding = "live"
                for node in (items or [])[:40]:
                    evidence.append(
                        self._evidence(
                            type="k8s_node",
                            title=str(node.get("name") or "node"),
                            source="kubernetes",
                            snippet=json.dumps(node, default=str)[:800],
                        )
                    )
            else:
                aws_items: list = []
                k8s_pods: list = []
                if wants_aws or (not wants_k8s):
                    if aws is not None:
                        aws_items = await aws.list_instances(region)
                        aws_ok = True
                        for inst in aws_items[:20]:
                            evidence.append(
                                self._evidence(
                                    type="ec2_instance",
                                    title=str(inst.get("name_tag") or inst.get("id") or "instance"),
                                    source="aws",
                                    snippet=json.dumps(inst, default=str)[:600],
                                )
                            )
                    else:
                        errors.append("aws_not_configured")
                if k8s is not None:
                    k8s_pods = await k8s.list_pods(namespace)
                    k8s_ok = True
                    for pod in k8s_pods[:20]:
                        evidence.append(
                            self._evidence(
                                type="k8s_pod",
                                title=str(pod.get("name") or "pod"),
                                source="kubernetes",
                                snippet=json.dumps(pod, default=str)[:600],
                            )
                        )
                elif wants_k8s:
                    errors.append("kubernetes_not_configured")
                resource_type = "mixed"
                items = {"ec2_instances": aws_items, "pods": k8s_pods}
                if k8s is None:
                    items["kubernetes_status"] = "not_configured"
                if aws_ok and k8s_ok:
                    grounding = "live"
                elif aws_ok or k8s_ok:
                    grounding = "partial"
                else:
                    return self._no_data_result(
                        context,
                        "No live infra connectors available (AWS/Kubernetes).",
                        missing_tools=["AWS", "Kubernetes"],
                    )
        except Exception as exc:
            return self._result(
                context,
                status="failed",
                summary="Infrastructure scan failed",
                details={"error": str(exc)[:300], "environment": env},
                grounding="none",
                confidence=0.0,
                errors=[str(exc)[:300]],
            )

        # Mutating intents (scale/delete) — plan commands via policy, never raw execute.
        commands: list[str] = []
        if wants_mutate and k8s_ok:
            target = params.get("deployment") or params.get("name") or params.get("pod_name")
            replicas = params.get("replicas")
            if re.search(r"\bscale\b", task) and target:
                commands.append(
                    f"kubectl scale deployment/{target} --replicas={replicas or 1} -n {namespace}"
                )
            if re.search(r"\bdelete\b", task) and target:
                kind = "pod" if "pod" in task else "deployment"
                commands.append(f"kubectl delete {kind}/{target} -n {namespace}")

        count = len(items) if isinstance(items, list) else sum(
            len(v) for v in items.values() if isinstance(v, list)
        )

        if commands:
            return self._finalize_with_policy(
                context,
                summary=f"Infrastructure {resource_type} plan ({count} items observed)",
                details={
                    "resource_type": resource_type,
                    "count": count,
                    "items": items,
                    "environment": env,
                },
                commands=commands,
                evidence=evidence,
                grounding=grounding or "partial",
                confidence=0.75,
                task=task[:200],
            )

        return self._result(
            context,
            status="success",
            summary=f"Infrastructure scan: {resource_type} ({count} items)",
            details={
                "resource_type": resource_type,
                "count": count,
                "items": items,
                "environment": env,
            },
            evidence=evidence,
            grounding=grounding or "live",
            confidence=0.8,
            errors=errors,
        )


infra_agent = InfraAgent()
