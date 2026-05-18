"""AWS connector — EC2, Cost Explorer, Security Hub via boto3."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import boto3

from .registry import AWSConnector as _BaseAws


class AWSConnector(_BaseAws):
    def _session(self, region: str | None = None):
        return boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=region or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        )

    async def list_instances(self, region: str | None = None) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            ec2 = self._session(region).client("ec2")
            paginator = ec2.get_paginator("describe_instances")
            out: list[dict[str, Any]] = []
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        name_tag = ""
                        for tag in inst.get("Tags") or []:
                            if tag.get("Key") == "Name":
                                name_tag = tag.get("Value", "")
                                break
                        launch = inst.get("LaunchTime")
                        out.append(
                            {
                                "id": inst.get("InstanceId"),
                                "type": inst.get("InstanceType"),
                                "state": (inst.get("State") or {}).get("Name"),
                                "name_tag": name_tag,
                                "launch_time": launch.isoformat() if launch else None,
                            }
                        )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def get_cost_explorer(
        self,
        start: str,
        end: str,
        granularity: str = "MONTHLY",
    ) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            ce = self._session().client("ce")
            resp = ce.get_cost_and_usage(
                TimePeriod={"Start": start, "End": end},
                Granularity=granularity,
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
            out: list[dict[str, Any]] = []
            for period in resp.get("ResultsByTime", []):
                for group in period.get("Groups", []):
                    keys = group.get("Keys") or []
                    amount_obj = (group.get("Metrics") or {}).get("UnblendedCost") or {}
                    out.append(
                        {
                            "service": keys[0] if keys else "unknown",
                            "amount": amount_obj.get("Amount", "0"),
                            "unit": amount_obj.get("Unit", "USD"),
                        }
                    )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def list_security_findings(self) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            sh = self._session().client("securityhub")
            resp = sh.get_findings(
                Filters={
                    "SeverityLabel": [
                        {"Value": "CRITICAL", "Comparison": "EQUALS"},
                        {"Value": "HIGH", "Comparison": "EQUALS"},
                    ]
                },
                MaxResults=100,
            )
            out: list[dict[str, Any]] = []
            for finding in resp.get("Findings", []):
                resources = finding.get("Resources") or []
                resource = resources[0].get("Id") if resources else ""
                out.append(
                    {
                        "title": finding.get("Title"),
                        "severity": (finding.get("Severity") or {}).get("Label"),
                        "resource": resource,
                        "description": finding.get("Description"),
                    }
                )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            if action == "list_instances":
                result = await self.list_instances(params.get("region"))
                return {"ok": True, "tool": "aws", "action": action, "result": result}
            if action == "get_cost_explorer":
                result = await self.get_cost_explorer(
                    params.get("start", ""),
                    params.get("end", ""),
                    params.get("granularity", "MONTHLY"),
                )
                return {"ok": True, "tool": "aws", "action": action, "result": result}
            if action == "list_security_findings":
                result = await self.list_security_findings()
                return {"ok": True, "tool": "aws", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "aws", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
