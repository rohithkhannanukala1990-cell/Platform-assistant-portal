"""Infra agent — EC2, pods, and nodes inventory."""

from __future__ import annotations

import re

from sqlmodel import Session

from ..connectors.aws_connector import AWSConnector
from ..connectors.kubernetes_connector import KubernetesConnector
from ..context import PlatformContext
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

        resource_type = "mixed"
        items: list = []

        try:
            if re.search(r"\bec2|instance|aws\b", task):
                resource_type = "ec2"
                items = await AWSConnector(_ACCOUNT).list_instances(region)
            elif re.search(r"\bpod|pods\b", task):
                resource_type = "pods"
                items = await KubernetesConnector(_ACCOUNT).list_pods(namespace)
            elif re.search(r"\bnode|nodes|scale\b", task):
                resource_type = "nodes"
                items = await KubernetesConnector(_ACCOUNT).list_nodes()
            else:
                aws_items = await AWSConnector(_ACCOUNT).list_instances(region)
                k8s_pods = await KubernetesConnector(_ACCOUNT).list_pods(namespace)
                resource_type = "mixed"
                items = {"ec2_instances": aws_items, "pods": k8s_pods}
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
