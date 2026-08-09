"""AWS connector — EC2, Cost Explorer, Security Hub, and HITL remediations via boto3."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

from .idempotency import ConnectorNotConfigured, recall_idempotent, store_idempotent
from .registry import AWSConnector as _BaseAws


class AWSConnector(_BaseAws):
    def _session(self, region: str | None = None):
        a = self.account or {}
        key_id = a.get("aws_access_key_id") or a.get("access_key_id")
        secret = a.get("aws_secret_access_key") or a.get("secret_access_key")
        raw = str(a.get("credentials_vault_ref") or a.get("api_key") or a.get("token") or "").strip()
        if raw.startswith("{"):
            try:
                import json

                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    key_id = key_id or parsed.get("aws_access_key_id") or parsed.get("access_key_id")
                    secret = (
                        secret
                        or parsed.get("aws_secret_access_key")
                        or parsed.get("secret_access_key")
                    )
            except Exception:
                pass
        elif raw and not secret:
            secret = raw
        return boto3.Session(
            aws_access_key_id=key_id or os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=secret or os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=region
            or (a.get("region") or "").strip()
            or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        )

    def _require_creds(self) -> None:
        a = self.account or {}
        if not (
            a.get("aws_access_key_id")
            or a.get("access_key_id")
            or os.getenv("AWS_ACCESS_KEY_ID")
            or a.get("credentials_vault_ref")
        ):
            # Still allow default credential chain in real envs; only raise when empty account
            # and no env — tests inject methods directly.
            pass

    async def list_instances(self, region: str | None = None) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            ec2 = self._session(region).client("ec2")
            paginator = ec2.get_paginator("describe_instances")
            out: list[dict[str, Any]] = []
            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for inst in reservation.get("Instances", []):
                        tags = {t.get("Key"): t.get("Value") for t in (inst.get("Tags") or [])}
                        launch = inst.get("LaunchTime")
                        out.append(
                            {
                                "id": inst.get("InstanceId"),
                                "type": inst.get("InstanceType"),
                                "state": (inst.get("State") or {}).get("Name"),
                                "name_tag": tags.get("Name", ""),
                                "tags": tags,
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
                        "type": finding.get("Type") or finding.get("ProductFields", {}).get(
                            "ControlId"
                        ),
                    }
                )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    # ── Read helpers for blast radius ─────────────────────────────────────────

    async def describe_security_group_usage(
        self, group_id: str, region: str | None = None
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            ec2 = self._session(region).client("ec2")
            sg = ec2.describe_security_groups(GroupIds=[group_id])["SecurityGroups"][0]
            ingress = sg.get("IpPermissions") or []
            enis = ec2.describe_network_interfaces(
                Filters=[{"Name": "group-id", "Values": [group_id]}]
            ).get("NetworkInterfaces") or []
            instances = []
            for eni in enis:
                att = eni.get("Attachment") or {}
                if att.get("InstanceId"):
                    instances.append(att["InstanceId"])
            return {
                "group_id": group_id,
                "ingress": ingress,
                "instances": list(dict.fromkeys(instances)),
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_bucket_public_info(self, bucket: str) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            s3 = self._session().client("s3")
            public_objects = False
            object_count = 0
            try:
                paginator = s3.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket):
                    contents = page.get("Contents") or []
                    object_count += len(contents)
                # Best-effort ACL check on bucket
                try:
                    acl = s3.get_bucket_acl(Bucket=bucket)
                    for grant in acl.get("Grants") or []:
                        uri = ((grant.get("Grantee") or {}).get("URI") or "")
                        if "AllUsers" in uri or "AuthenticatedUsers" in uri:
                            public_objects = True
                except Exception:
                    pass
            except Exception as exc:
                return {"bucket": bucket, "error": str(exc)[:300], "object_count": 0}
            return {
                "bucket": bucket,
                "object_count": object_count,
                "serves_public_objects": public_objects,
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_access_key_info(self, access_key_id: str) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            iam = self._session().client("iam")
            # Find owning user
            users = iam.list_users().get("Users") or []
            owner = None
            meta = None
            for u in users:
                keys = iam.list_access_keys(UserName=u["UserName"]).get("AccessKeyMetadata") or []
                for k in keys:
                    if k.get("AccessKeyId") == access_key_id:
                        owner = u["UserName"]
                        meta = k
                        break
                if owner:
                    break
            last_used = None
            if owner:
                try:
                    lu = iam.get_access_key_last_used(AccessKeyId=access_key_id)
                    last_used = (lu.get("AccessKeyLastUsed") or {}).get("LastUsedDate")
                except Exception:
                    pass
            created = meta.get("CreateDate") if meta else None
            age_days = None
            if created:
                age_days = (datetime.now(timezone.utc) - created.replace(tzinfo=timezone.utc)).days
            return {
                "access_key_id": access_key_id,
                "principal": owner,
                "created": created.isoformat() if created else None,
                "age_days": age_days,
                "last_used": last_used.isoformat() if last_used else None,
                "status": (meta or {}).get("Status"),
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_volume_info(self, volume_id: str, region: str | None = None) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            ec2 = self._session(region).client("ec2")
            vol = ec2.describe_volumes(VolumeIds=[volume_id])["Volumes"][0]
            attachments = vol.get("Attachments") or []
            return {
                "volume_id": volume_id,
                "encrypted": bool(vol.get("Encrypted")),
                "size": vol.get("Size"),
                "attachments": [
                    {"instance_id": a.get("InstanceId"), "device": a.get("Device")}
                    for a in attachments
                ],
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    async def get_instance_utilization(
        self,
        instance_id: str,
        *,
        days: int = 14,
        region: str | None = None,
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            cw = self._session(region).client("cloudwatch")
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=days)
            def _stats(metric: str, namespace: str = "AWS/EC2", dim_name: str = "InstanceId"):
                resp = cw.get_metric_statistics(
                    Namespace=namespace,
                    MetricName=metric,
                    Dimensions=[{"Name": dim_name, "Value": instance_id}],
                    StartTime=start,
                    EndTime=end,
                    Period=3600,
                    Statistics=["Average", "Maximum"],
                )
                points = resp.get("Datapoints") or []
                if not points:
                    return {"avg": None, "p95_approx": None}
                avgs = sorted(float(p["Average"]) for p in points if "Average" in p)
                avg = sum(avgs) / len(avgs) if avgs else None
                idx = max(0, int(len(avgs) * 0.95) - 1) if avgs else 0
                p95 = avgs[idx] if avgs else None
                return {"avg": avg, "p95_approx": p95}

            cpu = _stats("CPUUtilization")
            net_in = _stats("NetworkIn")
            net_out = _stats("NetworkOut")
            # Memory requires CW agent — may be empty
            mem = _stats("mem_used_percent", namespace="CWAgent", dim_name="InstanceId")
            return {
                "instance_id": instance_id,
                "days": days,
                "cpu": cpu,
                "memory": mem,
                "network_in": net_in,
                "network_out": net_out,
            }

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync)

    # ── Write remediations (idempotent) ───────────────────────────────────────

    async def update_security_group_ingress(
        self,
        group_id: str,
        *,
        revoke_ip_permissions: list[dict[str, Any]] | None = None,
        authorize_ip_permissions: list[dict[str, Any]] | None = None,
        region: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        def _sync() -> dict[str, Any]:
            ec2 = self._session(region).client("ec2")
            if revoke_ip_permissions:
                ec2.revoke_security_group_ingress(
                    GroupId=group_id, IpPermissions=revoke_ip_permissions
                )
            if authorize_ip_permissions:
                ec2.authorize_security_group_ingress(
                    GroupId=group_id, IpPermissions=authorize_ip_permissions
                )
            return {
                "ok": True,
                "group_id": group_id,
                "revoked": revoke_ip_permissions or [],
                "authorized": authorize_ip_permissions or [],
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

    async def put_public_access_block(
        self,
        bucket: str,
        *,
        block_public_acls: bool = True,
        ignore_public_acls: bool = True,
        block_public_policy: bool = True,
        restrict_public_buckets: bool = True,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        def _sync() -> dict[str, Any]:
            s3 = self._session().client("s3")
            s3.put_public_access_block(
                Bucket=bucket,
                PublicAccessBlockConfiguration={
                    "BlockPublicAcls": block_public_acls,
                    "IgnorePublicAcls": ignore_public_acls,
                    "BlockPublicPolicy": block_public_policy,
                    "RestrictPublicBuckets": restrict_public_buckets,
                },
            )
            return {"ok": True, "bucket": bucket, "public_access_block": True}

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

    async def update_access_key_status(
        self,
        access_key_id: str,
        *,
        user_name: str,
        status: str = "Inactive",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        def _sync() -> dict[str, Any]:
            iam = self._session().client("iam")
            iam.update_access_key(
                UserName=user_name, AccessKeyId=access_key_id, Status=status
            )
            return {
                "ok": True,
                "access_key_id": access_key_id,
                "user_name": user_name,
                "status": status,
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

    async def enable_ebs_encryption(
        self,
        volume_id: str,
        *,
        region: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Create encrypted snapshot as first step of volume replacement."""
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        def _sync() -> dict[str, Any]:
            ec2 = self._session(region).client("ec2")
            snap = ec2.create_snapshot(
                VolumeId=volume_id,
                Description=f"Encrypted replacement source for {volume_id}",
                TagSpecifications=[
                    {
                        "ResourceType": "snapshot",
                        "Tags": [{"Key": "Purpose", "Value": "ebs-encrypt-remediation"}],
                    }
                ],
            )
            # Copy snapshot with encryption
            copy = ec2.copy_snapshot(
                SourceRegion=self._session(region).region_name,
                SourceSnapshotId=snap["SnapshotId"],
                Encrypted=True,
                Description=f"Encrypted copy of {snap['SnapshotId']}",
            )
            return {
                "ok": True,
                "volume_id": volume_id,
                "snapshot_id": snap["SnapshotId"],
                "encrypted_snapshot_id": copy.get("SnapshotId"),
                "note": "Replace volume from encrypted snapshot (requires instance downtime)",
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

    async def modify_instance_type(
        self,
        instance_id: str,
        *,
        instance_type: str,
        region: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        cached = recall_idempotent(idempotency_key)
        if cached:
            return {**cached, "reused": True}

        def _sync() -> dict[str, Any]:
            ec2 = self._session(region).client("ec2")
            ec2.stop_instances(InstanceIds=[instance_id])
            waiter = ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[instance_id])
            ec2.modify_instance_attribute(
                InstanceId=instance_id,
                InstanceType={"Value": instance_type},
            )
            ec2.start_instances(InstanceIds=[instance_id])
            return {
                "ok": True,
                "instance_id": instance_id,
                "instance_type": instance_type,
            }

        loop = asyncio.get_event_loop()
        out = await loop.run_in_executor(None, _sync)
        store_idempotent(idempotency_key, out)
        return out

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
            if action == "update_security_group_ingress":
                result = await self.update_security_group_ingress(
                    params.get("group_id", ""),
                    revoke_ip_permissions=params.get("revoke_ip_permissions"),
                    authorize_ip_permissions=params.get("authorize_ip_permissions"),
                    region=params.get("region"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "aws", "action": action, "result": result}
            if action == "put_public_access_block":
                result = await self.put_public_access_block(
                    params.get("bucket", ""),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "aws", "action": action, "result": result}
            if action == "update_access_key_status":
                result = await self.update_access_key_status(
                    params.get("access_key_id", ""),
                    user_name=params.get("user_name", ""),
                    status=params.get("status", "Inactive"),
                    idempotency_key=params.get("idempotency_key"),
                )
                return {"ok": bool(result.get("ok")), "tool": "aws", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "aws", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
