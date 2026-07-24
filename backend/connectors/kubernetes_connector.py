"""Kubernetes connector — pods, nodes, deploy, restart (account-scoped credentials)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .registry import KubernetesConnector as _BaseK8s


def _age_seconds(created: datetime | None) -> int | None:
    if not created:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return int((datetime.now(timezone.utc) - created).total_seconds())


class KubernetesConnector(_BaseK8s):
    def __init__(self, account: dict[str, Any]):
        super().__init__(account)
        self.v1: client.CoreV1Api | None = None
        self.apps_v1: client.AppsV1Api | None = None
        self.configured = False
        self._init_error: str | None = None
        self._init_client()

    def _cred_blob(self) -> str:
        return (
            self.account.get("kubeconfig")
            or self.account.get("credentials_vault_ref")
            or self.account.get("token")
            or self.account.get("api_token")
            or ""
        ).strip()

    def _init_client(self) -> None:
        creds = self._cred_blob()
        auth_type = (self.account.get("auth_type") or "").lower()
        server = (self.account.get("instance_url") or "").strip()
        tmp_path: str | None = None
        try:
            if creds and ("apiVersion:" in creds or "clusters:" in creds or "kind: Config" in creds):
                fd, tmp_path = tempfile.mkstemp(suffix=".kubeconfig")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(creds)
                config.load_kube_config(config_file=tmp_path)
            elif creds and (os.path.isfile(creds) or creds.endswith(".kubeconfig")):
                config.load_kube_config(config_file=creds)
            elif auth_type in {"service_account", "token", "bearer", "oidc"} and creds and server:
                configuration = client.Configuration()
                configuration.host = server.rstrip("/")
                configuration.verify_ssl = True
                configuration.api_key = {"authorization": creds}
                configuration.api_key_prefix = {"authorization": "Bearer"}
                api_client = client.ApiClient(configuration)
                self.v1 = client.CoreV1Api(api_client)
                self.apps_v1 = client.AppsV1Api(api_client)
                self.configured = True
                return
            elif creds:
                # Treat as kubeconfig path or bare token without server — try default load
                try:
                    config.load_kube_config(config_file=creds)
                except Exception:
                    config.load_incluster_config()
            else:
                # No ToolAccount credentials: allow in-cluster / local kubeconfig for probes only
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

            self.v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.configured = True
        except Exception as exc:
            self._init_error = str(exc)
            self.v1 = None
            self.apps_v1 = None
            self.configured = False
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def ping(self) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            if not self.configured:
                return {
                    "ok": False,
                    "error": {
                        "type": "not_configured",
                        "message": self._init_error or "Kubernetes client not configured",
                    },
                }
            version = client.VersionApi().get_code()
            return {
                "ok": True,
                "git_version": getattr(version, "git_version", None),
            }

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception as exc:
            return {
                "ok": False,
                "error": {"type": "network_error", "message": str(exc)},
            }

    async def list_namespaces(self) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            if not self.v1:
                return []
            resp = self.v1.list_namespace()
            return [
                {
                    "name": ns.metadata.name,
                    "status": (ns.status.phase if ns.status else None),
                    "age_seconds": _age_seconds(ns.metadata.creation_timestamp),
                }
                for ns in resp.items
            ]

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def list_pods(self, namespace: str = "default") -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            if not self.v1:
                return []
            resp = self.v1.list_namespaced_pod(namespace=namespace)
            out: list[dict[str, Any]] = []
            for pod in resp.items:
                restarts = 0
                for cs in pod.status.container_statuses or []:
                    restarts += cs.restart_count or 0
                out.append(
                    {
                        "name": pod.metadata.name,
                        "status": pod.status.phase,
                        "restarts": restarts,
                        "node": pod.spec.node_name,
                        "age_seconds": _age_seconds(pod.metadata.creation_timestamp),
                    }
                )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def list_nodes(self) -> list[dict[str, Any]]:
        def _sync() -> list[dict[str, Any]]:
            if not self.v1:
                return []
            resp = self.v1.list_node()
            out: list[dict[str, Any]] = []
            for node in resp.items:
                labels = node.metadata.labels or {}
                roles = [
                    k.replace("node-role.kubernetes.io/", "")
                    for k in labels
                    if k.startswith("node-role.kubernetes.io/")
                ]
                capacity = node.status.capacity or {}
                ready = "NotReady"
                for cond in node.status.conditions or []:
                    if cond.type == "Ready" and cond.status == "True":
                        ready = "Ready"
                        break
                out.append(
                    {
                        "name": node.metadata.name,
                        "status": ready,
                        "roles": roles or ["worker"],
                        "cpu": capacity.get("cpu"),
                        "memory": capacity.get("memory"),
                    }
                )
            return out

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return []

    async def deploy(
        self,
        service_name: str,
        image_tag: str,
        namespace: str = "default",
    ) -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            if not self.apps_v1:
                return {"success": False, "message": "Kubernetes client not configured"}
            deployment = self.apps_v1.read_namespaced_deployment(service_name, namespace)
            containers = deployment.spec.template.spec.containers
            if not containers:
                return {"success": False, "message": "No containers in deployment"}
            containers[0].image = image_tag
            self.apps_v1.patch_namespaced_deployment(
                name=service_name,
                namespace=namespace,
                body=deployment,
            )
            return {"success": True, "message": f"Updated {service_name} to {image_tag}"}

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except ApiException as exc:
            return {"success": False, "message": str(exc.body or exc.reason)}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    async def restart_pod(self, pod_name: str, namespace: str = "default") -> dict[str, Any]:
        def _sync() -> dict[str, Any]:
            if not self.v1:
                return {"success": False}
            self.v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
            return {"success": True}

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _sync)
        except Exception:
            return {"success": False}

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        try:
            ns = params.get("namespace", "default")
            if action == "ping":
                result = await self.ping()
                return {"ok": bool(result.get("ok")), "tool": "kubernetes", "action": action, "result": result}
            if action == "list_namespaces":
                result = await self.list_namespaces()
                return {"ok": True, "tool": "kubernetes", "action": action, "result": result}
            if action == "list_pods":
                result = await self.list_pods(ns)
                return {"ok": True, "tool": "kubernetes", "action": action, "result": result}
            if action == "list_nodes":
                result = await self.list_nodes()
                return {"ok": True, "tool": "kubernetes", "action": action, "result": result}
            if action == "deploy":
                result = await self.deploy(
                    params.get("service_name", ""),
                    params.get("image_tag", ""),
                    ns,
                )
                return {"ok": result.get("success", False), "tool": "kubernetes", "action": action, "result": result}
            if action == "restart_pod":
                result = await self.restart_pod(params.get("pod_name", ""), ns)
                return {"ok": result.get("success", False), "tool": "kubernetes", "action": action, "result": result}
        except Exception as exc:
            return {"ok": False, "tool": "kubernetes", "action": action, "error": str(exc)}
        return await super().execute_action(action, params)
