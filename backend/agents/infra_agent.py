"""Infra agent — EC2, pods, and nodes inventory."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..connectors.aws_connector import AWSConnector
from ..context import PlatformContext
from ..services.k8s_access import try_k8s_connector_from_context
from .base import BaseAgent

_ACCOUNT: dict = {}


class InfraAgent(BaseAgent):
    name = "infra_agent"
    description = "Terraform/Pulumi infrastructure changes across cloud providers."
    requires_approval_envs = ["production"]
    primary_tools = ["Terraform", "Pulumi", "AWS", "GCP", "Azure"]

    async def run(self, params: dict, context: PlatformContext, db: Session):
        task = (params.get("task") or params.get("message") or "").lower()
        namespace = params.get("namespace") or "default"
        region = params.get("region")
        env = (context.environment or "development").lower()

        wants_k8s = bool(
            re.search(r"\bpod|pods|node|nodes|scale|k8s|kubernetes\b", task)
            or not re.search(r"\bec2|instance|aws\b", task)
        )
        wants_aws = bool(re.search(r"\bec2|instance|aws\b", task) or not wants_k8s)

        k8s = try_k8s_connector_from_context(context, db=db) if wants_k8s else None
        if wants_k8s and k8s is None and not re.search(r"\bec2|instance|aws\b", task):
            return self._build_result(
                context,
                status="skipped",
                summary="Kubernetes not connected. Connect a Kubernetes account in Tool Registry.",
                details={
                    "resource_type": "pods",
                    "count": 0,
                    "items": [],
                    "environment": env,
                    "reason": "kubernetes_not_configured",
                },
            )

        resource_type = "mixed"
        items: list | dict = []

        try:
            if re.search(r"\bec2|instance|aws\b", task):
                resource_type = "ec2"
                items = await AWSConnector(_ACCOUNT).list_instances(region)
            elif re.search(r"\bpod|pods\b", task):
                resource_type = "pods"
                items = await k8s.list_pods(namespace) if k8s else []
            elif re.search(r"\bnode|nodes|scale\b", task):
                resource_type = "nodes"
                items = await k8s.list_nodes() if k8s else []
            else:
                aws_items = await AWSConnector(_ACCOUNT).list_instances(region) if wants_aws else []
                k8s_pods = await k8s.list_pods(namespace) if k8s else []
                resource_type = "mixed"
                items = {"ec2_instances": aws_items, "pods": k8s_pods}
                if k8s is None:
                    items["kubernetes_status"] = "not_configured"
        except Exception:
            items = []

        count = len(items) if isinstance(items, list) else sum(
            len(v) for v in items.values() if isinstance(v, list)
        )

        return self._build_result(
            context,
            status="success",
            summary=f"Infrastructure scan: {resource_type} ({count} items)",
            details={
                "resource_type": resource_type,
                "count": count,
                "items": items,
                "environment": env,
            },
        )


infra_agent = InfraAgent()
