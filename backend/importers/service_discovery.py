import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


class ServiceDiscovery:
    async def discover_from_github(self, account: dict) -> Dict[str, Any]:
        orgs_found = [
            {"name": "my-org", "repos": 45, "members": 12},
            {"name": "my-org-infrastructure", "repos": 8, "members": 5},
        ]
        suggestions = []
        for org in orgs_found:
            suggestions.append(
                {
                    "id": str(uuid.uuid4()),
                    "tool_id": "github",
                    "account_name": f"GitHub {org['name']}",
                    "environment": "production",
                    "account_identifier": org["name"],
                    "instance_url": "https://github.com",
                    "auth_type": "pat",
                    "requires_hitl": False,
                    "status": "unknown",
                    "is_active": 1,
                    "created_by": "service_discovery",
                    "created_at": datetime.now(timezone.utc),
                    "metadata": {"repos": org["repos"], "members": org["members"]},
                }
            )
        return {
            "source": "github",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_from_jira(self, account: dict) -> Dict[str, Any]:
        projects_found = [
            {"key": "ENG", "name": "Engineering", "issues": 234},
            {"key": "OPS", "name": "Operations", "issues": 89},
            {"key": "INFRA", "name": "Infrastructure", "issues": 156},
        ]
        suggestions = []
        for proj in projects_found:
            suggestions.append(
                {
                    "id": str(uuid.uuid4()),
                    "tool_id": "jira",
                    "account_name": f"Jira {proj['name']}",
                    "environment": (account.get("environment") or "production").lower(),
                    "account_identifier": account.get("account_identifier") or "",
                    "instance_url": account.get("instance_url") or "",
                    "auth_type": account.get("auth_type") or "api_token",
                    "requires_hitl": False,
                    "status": "unknown",
                    "is_active": 1,
                    "created_by": "service_discovery",
                    "created_at": datetime.now(timezone.utc),
                    "metadata": {"project_key": proj["key"], "open_issues": proj["issues"]},
                }
            )
        return {
            "source": "jira",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_from_slack(self, account: dict) -> Dict[str, Any]:
        channels_found = [
            {"name": "incidents", "members": 45},
            {"name": "deployments", "members": 32},
            {"name": "alerts", "members": 67},
            {"name": "oncall", "members": 18},
        ]
        suggestions = [
            {
                "id": str(uuid.uuid4()),
                "tool_id": "slack",
                "account_name": f"Slack {account.get('account_identifier', 'Workspace')}",
                "environment": (account.get("environment") or "production").lower(),
                "account_identifier": account.get("account_identifier") or "",
                "instance_url": account.get("instance_url") or None,
                "auth_type": "bot_token",
                "requires_hitl": False,
                "status": "unknown",
                "is_active": 1,
                "created_by": "service_discovery",
                "created_at": datetime.now(timezone.utc),
                "metadata": {"channels": channels_found, "channel_count": len(channels_found)},
            }
        ]
        return {
            "source": "slack",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_from_kubernetes(self, account: dict) -> Dict[str, Any]:
        namespaces = [
            {"name": "default", "pods": 12},
            {"name": "production", "pods": 45},
            {"name": "staging", "pods": 23},
            {"name": "monitoring", "pods": 8},
            {"name": "ingress-nginx", "pods": 3},
        ]
        suggestions = []
        ident = account.get("account_identifier") or ""
        for ns in namespaces:
            name = ns["name"]
            env = (
                "production"
                if name == "production"
                else "staging"
                if name == "staging"
                else "development"
            )
            suggestions.append(
                {
                    "id": str(uuid.uuid4()),
                    "tool_id": "kubernetes",
                    "account_name": f"K8s {ident} / {name}",
                    "environment": env,
                    "account_identifier": ident,
                    "instance_url": account.get("instance_url") or None,
                    "auth_type": account.get("auth_type") or "kubeconfig",
                    "requires_hitl": env == "production",
                    "status": "unknown",
                    "is_active": 1,
                    "created_by": "service_discovery",
                    "created_at": datetime.now(timezone.utc),
                    "metadata": {"namespace": name, "pod_count": ns["pods"]},
                }
            )
        return {
            "source": "kubernetes",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_from_datadog(self, account: dict) -> Dict[str, Any]:
        suggestions = [
            {
                "id": str(uuid.uuid4()),
                "tool_id": "datadog",
                "account_name": f"Datadog {account.get('account_identifier', 'Prod')}",
                "environment": (account.get("environment") or "production").lower(),
                "account_identifier": account.get("account_identifier") or "",
                "instance_url": account.get("instance_url") or None,
                "auth_type": "api_key_app_key",
                "requires_hitl": False,
                "status": "unknown",
                "is_active": 1,
                "created_by": "service_discovery",
                "created_at": datetime.now(timezone.utc),
                "metadata": {"monitors": 45, "dashboards": 12, "alerts_active": 3},
            }
        ]
        return {
            "source": "datadog",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_all_from_connected(self, connected_accounts: List[dict]) -> Dict[str, Any]:
        """Aggregate stub suggestions for each supported connected integration."""
        all_discovered: List[dict] = []
        scanned = 0
        for account in connected_accounts:
            tool_id = (account.get("tool_id") or "").strip().lower()
            if tool_id == "github":
                result = await self.discover_from_github(dict(account))
            elif tool_id == "jira":
                result = await self.discover_from_jira(dict(account))
            elif tool_id == "slack":
                result = await self.discover_from_slack(dict(account))
            elif tool_id == "kubernetes":
                result = await self.discover_from_kubernetes(dict(account))
            elif tool_id == "datadog":
                result = await self.discover_from_datadog(dict(account))
            else:
                continue
            scanned += 1
            all_discovered.extend(result.get("discovered") or [])
        return {
            "total_discovered": len(all_discovered),
            "accounts": all_discovered,
            "sources_scanned": scanned,
        }


service_discovery = ServiceDiscovery()
