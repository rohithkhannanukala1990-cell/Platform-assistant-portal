"""Per-tool connector metadata and simulated test_connection() implementations."""

from __future__ import annotations

import asyncio
import time
from typing import Any

CONNECTOR_MAP: dict[str, dict[str, Any]] = {
    "aws": {
        "auth_types": ["iam_role", "access_keys", "sso"],
        "required_fields": ["region"],
        "optional_fields": ["account_id", "role_arn"],
        "default_region": "us-east-1",
    },
    "gcp": {
        "auth_types": ["service_account", "workload_identity", "oauth2"],
        "required_fields": ["project_id"],
        "optional_fields": ["region", "zone"],
    },
    "azure": {
        "auth_types": ["client_secret", "managed_identity", "certificate"],
        "required_fields": ["tenant_id", "client_id"],
        "optional_fields": ["subscription_id"],
    },
    "github": {
        "auth_types": ["pat", "github_app", "oauth2"],
        "required_fields": ["instance_url"],
        "optional_fields": ["org_name"],
    },
    "gitlab": {
        "auth_types": ["pat", "oauth2"],
        "required_fields": ["instance_url"],
        "optional_fields": ["group_name"],
    },
    "jira": {
        "auth_types": ["api_token", "oauth2", "basic"],
        "required_fields": ["instance_url", "account_identifier"],
        "optional_fields": [],
    },
    "confluence": {
        "auth_types": ["api_token", "basic"],
        "required_fields": ["instance_url", "account_identifier"],
        "optional_fields": [],
    },
    "slack": {
        "auth_types": ["bot_token", "oauth2", "webhook"],
        "required_fields": [],
        "optional_fields": ["workspace_name"],
    },
    "pagerduty": {
        "auth_types": ["api_key", "user_token"],
        "required_fields": [],
        "optional_fields": ["subdomain"],
    },
    "datadog": {
        "auth_types": ["api_key_app_key"],
        "required_fields": [],
        "optional_fields": ["site", "region"],
    },
    "prometheus": {
        "auth_types": ["basic", "bearer_token", "none"],
        "required_fields": ["instance_url"],
        "optional_fields": [],
    },
    "grafana": {
        "auth_types": ["service_account", "api_key", "basic"],
        "required_fields": ["instance_url"],
        "optional_fields": [],
    },
    "kubernetes": {
        "auth_types": ["kubeconfig", "service_account", "oidc"],
        "required_fields": [],
        "optional_fields": ["cluster_name", "namespace"],
    },
    "postgres": {
        "auth_types": ["connection_string", "username_password"],
        "required_fields": ["instance_url"],
        "optional_fields": ["database_name", "ssl_mode"],
    },
    "vault": {
        "auth_types": ["token", "approle", "kubernetes"],
        "required_fields": ["instance_url"],
        "optional_fields": ["namespace", "mount_path"],
    },
    "argocd": {
        "auth_types": ["token", "bearer_token"],
        "required_fields": ["instance_url"],
        "optional_fields": [],
    },
    "outbound_webhook": {
        "auth_types": ["webhook", "api_key"],
        "required_fields": ["instance_url"],
        "optional_fields": [],
    },
    "servicenow": {
        "auth_types": ["webhook", "api_token", "oauth2"],
        "required_fields": [],
        "optional_fields": ["instance_url"],
    },
    "okta": {
        "auth_types": ["api_token"],
        "required_fields": ["instance_url"],
        "optional_fields": [],
    },
}


class ToolConnectionNotFound(Exception):
    pass


class BaseConnector:
    def __init__(self, account: dict[str, Any]):
        self.account = account
        self.tool_id = account.get("tool_id")

    async def execute_action(self, action: str, params: dict) -> dict[str, Any]:
        """Execute a tool-specific action (override in connector modules)."""
        await asyncio.sleep(0.05)
        return {
            "ok": True,
            "tool": self.tool_id,
            "action": action,
            "params": params,
            "message": f"Action '{action}' simulated for {self.tool_id}",
        }

    async def test_connection(self) -> dict[str, Any]:
        start = time.time()
        try:
            result = await self._do_test()
            latency = round((time.time() - start) * 1000, 2)
            return {
                "connected": result["connected"],
                "latency_ms": latency,
                "error": result.get("error"),
                "details": result.get("details", {}),
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "error": str(exc),
                "details": {},
            }

    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {"connected": True, "details": {}}


class AWSConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "connected": True,
            "details": {
                "region": self.account.get("region", "us-east-1"),
                "services": ["ec2", "s3", "eks"],
                "account_id": self.account.get("account_identifier"),
            },
        }


class GCPConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "connected": True,
            "details": {
                "project_id": self.account.get("account_identifier"),
                "services": ["gke", "gcs", "bigquery"],
            },
        }


class AzureConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "connected": True,
            "details": {
                "subscription_id": self.account.get("account_identifier"),
                "services": ["aks", "blob", "sql"],
            },
        }


class GitHubConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "connected": True,
            "details": {
                "instance_url": self.account.get("instance_url"),
                "org": self.account.get("account_identifier"),
                "scopes": ["repo", "workflow", "admin:org"],
            },
        }


class JiraConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "connected": True,
            "details": {
                "instance_url": self.account.get("instance_url"),
                "projects_count": 12,
            },
        }


class SlackConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "connected": True,
            "details": {
                "workspace": self.account.get("account_identifier"),
                "bot_scopes": ["chat:write", "channels:read"],
            },
        }


class PagerDutyConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.15)
        return {
            "connected": True,
            "details": {
                "services_count": 8,
                "schedules_count": 4,
            },
        }


class DatadogConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.2)
        return {
            "connected": True,
            "details": {
                "monitors_count": 45,
                "dashboards_count": 12,
            },
        }


class KubernetesConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.3)
        return {
            "connected": True,
            "details": {
                "cluster_name": self.account.get("account_identifier"),
                "nodes_count": 12,
                "namespaces": ["default", "production", "staging"],
            },
        }


class PostgresConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "connected": True,
            "details": {
                "version": "PostgreSQL 15.2",
                "database": self.account.get("account_identifier"),
                "ssl": True,
            },
        }


class VaultConnector(BaseConnector):
    async def _do_test(self) -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {
            "connected": True,
            "details": {
                "instance_url": self.account.get("instance_url"),
                "secret_engines": ["kv", "pki", "aws"],
            },
        }


CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {
    "aws": AWSConnector,
    "gcp": GCPConnector,
    "azure": AzureConnector,
    "oci": BaseConnector,
    "github": GitHubConnector,
    "gitlab": BaseConnector,
    "bitbucket": BaseConnector,
    "jira": JiraConnector,
    "linear": BaseConnector,
    "servicenow": BaseConnector,
    "slack": SlackConnector,
    "teams": BaseConnector,
    "pagerduty": PagerDutyConnector,
    "prometheus": BaseConnector,
    "datadog": DatadogConnector,
    "grafana": BaseConnector,
    "newrelic": BaseConnector,
    "postgres": PostgresConnector,
    "mysql": BaseConnector,
    "mongodb": BaseConnector,
    "redis": BaseConnector,
    "kubernetes": KubernetesConnector,
    "vault": VaultConnector,
    "aws_sm": BaseConnector,
    "jenkins": BaseConnector,
    "argocd": BaseConnector,
}


def get_connector(tool_id: str, account: dict[str, Any]) -> BaseConnector:
    if tool_id == "github":
        # Prefer the real HTTP connector implementation.
        from .github_connector import GitHubConnector as RealGitHubConnector

        return RealGitHubConnector(account)
    if tool_id == "kubernetes":
        from .kubernetes_connector import KubernetesConnector as RealK8sConnector

        return RealK8sConnector(account)
    if tool_id == "pagerduty":
        from .pagerduty_connector import PagerDutyConnector as RealPdConnector

        return RealPdConnector(account)
    if tool_id == "slack":
        from .slack_connector import SlackConnector as RealSlackConnector

        return RealSlackConnector(account)
    if tool_id == "prometheus":
        from .prometheus_connector import PrometheusConnector as RealPromConnector

        return RealPromConnector(account)
    if tool_id == "outbound_webhook":
        from .outbound_webhook_connector import OutboundWebhookConnector as RealOwConnector

        return RealOwConnector(account)
    if tool_id == "argocd":
        from .argocd_connector import ArgoCDConnector as RealArgoConnector

        return RealArgoConnector(account)
    if tool_id == "servicenow":
        from .servicenow_connector import ServiceNowConnector as RealSnowConnector

        return RealSnowConnector(account)
    if tool_id == "jira":
        from .jira_connector import JiraConnector as RealJiraConnector

        return RealJiraConnector(account)
    if tool_id == "confluence":
        from .confluence_connector import ConfluenceConnector as RealConfluenceConnector

        return RealConfluenceConnector(account)
    if tool_id == "okta":
        from .okta_connector import OktaConnector as RealOktaConnector

        return RealOktaConnector(account)
    connector_class = CONNECTOR_CLASSES.get(tool_id, BaseConnector)
    return connector_class(account)


def get_auth_types(tool_id: str) -> list[str]:
    config = CONNECTOR_MAP.get(tool_id, {})
    return list(config.get("auth_types", ["api_key"]))


def get_required_fields(tool_id: str) -> list[str]:
    config = CONNECTOR_MAP.get(tool_id, {})
    return list(config.get("required_fields", []))


def _connection_row_to_account(row) -> dict[str, Any]:
    import json

    cfg = json.loads(row.config or "{}")
    return {
        "tool_id": row.tool_id,
        "account_name": row.account_name,
        "account_identifier": row.account_alias,
        "account_alias": row.account_alias,
        "auth_type": row.auth_type,
        "region": cfg.get("region"),
        "instance_url": cfg.get("instance_url"),
        "status": row.status,
    }


def get_connector_for_account(tool_id: str, workspace_id: str, account_alias: str, db) -> BaseConnector:
    from ..database import get_tool_connection

    row = get_tool_connection(db, workspace_id, tool_id, account_alias)
    if not row:
        raise ToolConnectionNotFound(
            f"No connection for tool={tool_id} workspace={workspace_id} alias={account_alias}"
        )
    return get_connector(tool_id, _connection_row_to_account(row))


def list_accounts(tool_id: str, workspace_id: str, db) -> list[dict]:
    from ..database import get_tool_connections

    rows = get_tool_connections(db, workspace_id, tool_id)
    return [_connection_row_to_account(r) for r in rows if r.status == "connected"]


def get_default_account(tool_id: str, workspace_id: str, db) -> dict:
    from ..database import get_tool_connections

    accounts = list_accounts(tool_id, workspace_id, db)
    if accounts:
        return accounts[0]
    rows = get_tool_connections(db, workspace_id, tool_id)
    if not rows:
        raise ToolConnectionNotFound(f"No accounts for {tool_id} in workspace {workspace_id}")
    return _connection_row_to_account(rows[0])
