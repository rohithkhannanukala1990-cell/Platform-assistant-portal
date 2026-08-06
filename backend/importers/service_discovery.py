import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .environment_infer import apply_environment_to_account, requires_hitl_for_env


def _stamp(account: dict, *hints: Any, parent_env: str | None = None) -> dict:
    row = dict(account)
    # Re-infer from names/namespaces; parent account env is a soft default only.
    row.pop("environment", None)
    stamped = apply_environment_to_account(
        row,
        *hints,
        explicit=None,
        default=(parent_env or "development"),
    )
    # If inference fell back to default and parent had a specific env, prefer parent.
    if stamped.get("environment_source") == "default" and parent_env:
        stamped["environment"] = parent_env
        stamped["environment_source"] = "inherited"
        stamped["environment_confidence"] = "medium"
    stamped["requires_hitl"] = requires_hitl_for_env(stamped.get("environment"))
    return stamped


class ServiceDiscovery:
    async def discover_from_github(self, account: dict) -> Dict[str, Any]:
        orgs_found = [
            {"name": "my-org", "repos": 45, "members": 12},
            {"name": "my-org-infrastructure", "repos": 8, "members": 5},
            {"name": "my-org-staging", "repos": 6, "members": 4},
            {"name": "my-org-dev", "repos": 14, "members": 9},
        ]
        parent_env = (account.get("environment") or "").strip().lower() or None
        suggestions = []
        for org in orgs_found:
            row = {
                "id": str(uuid.uuid4()),
                "tool_id": "github",
                "account_name": f"GitHub {org['name']}",
                "account_identifier": org["name"],
                "instance_url": "https://github.com",
                "auth_type": "pat",
                "status": "unknown",
                "is_active": 1,
                "created_by": "service_discovery",
                "created_at": datetime.now(timezone.utc),
                "metadata": {"repos": org["repos"], "members": org["members"], "org": org["name"]},
            }
            suggestions.append(_stamp(row, org["name"], parent_env=parent_env))
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
            {"key": "QA", "name": "QA Test Board", "issues": 41},
        ]
        parent_env = (account.get("environment") or "").strip().lower() or None
        suggestions = []
        for proj in projects_found:
            row = {
                "id": str(uuid.uuid4()),
                "tool_id": "jira",
                "account_name": f"Jira {proj['name']}",
                "account_identifier": account.get("account_identifier") or "",
                "instance_url": account.get("instance_url") or "",
                "auth_type": account.get("auth_type") or "api_token",
                "status": "unknown",
                "is_active": 1,
                "created_by": "service_discovery",
                "created_at": datetime.now(timezone.utc),
                "metadata": {
                    "project_key": proj["key"],
                    "open_issues": proj["issues"],
                    "name": proj["name"],
                },
            }
            suggestions.append(
                _stamp(row, proj["name"], proj["key"], parent_env=parent_env)
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
        parent_env = (account.get("environment") or "").strip().lower() or None
        row = {
            "id": str(uuid.uuid4()),
            "tool_id": "slack",
            "account_name": f"Slack {account.get('account_identifier', 'Workspace')}",
            "account_identifier": account.get("account_identifier") or "",
            "instance_url": account.get("instance_url") or None,
            "auth_type": "bot_token",
            "status": "unknown",
            "is_active": 1,
            "created_by": "service_discovery",
            "created_at": datetime.now(timezone.utc),
            "metadata": {"channels": channels_found, "channel_count": len(channels_found)},
        }
        suggestions = [
            _stamp(
                row,
                account.get("account_name"),
                account.get("account_identifier"),
                parent_env=parent_env,
            )
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
            {"name": "dev", "pods": 18},
            {"name": "test", "pods": 11},
            {"name": "monitoring", "pods": 8},
            {"name": "ingress-nginx", "pods": 3},
        ]
        parent_env = (account.get("environment") or "").strip().lower() or None
        suggestions = []
        ident = account.get("account_identifier") or ""
        for ns in namespaces:
            name = ns["name"]
            row = {
                "id": str(uuid.uuid4()),
                "tool_id": "kubernetes",
                "account_name": f"K8s {ident} / {name}" if ident else f"K8s / {name}",
                "account_identifier": ident,
                "instance_url": account.get("instance_url") or None,
                "auth_type": account.get("auth_type") or "kubeconfig",
                "status": "unknown",
                "is_active": 1,
                "created_by": "service_discovery",
                "created_at": datetime.now(timezone.utc),
                "metadata": {"namespace": name, "pod_count": ns["pods"]},
            }
            suggestions.append(_stamp(row, name, ident, parent_env=parent_env))
        return {
            "source": "kubernetes",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_from_datadog(self, account: dict) -> Dict[str, Any]:
        parent_env = (account.get("environment") or "").strip().lower() or None
        ident = account.get("account_identifier") or "Org"
        row = {
            "id": str(uuid.uuid4()),
            "tool_id": "datadog",
            "account_name": f"Datadog {ident}",
            "account_identifier": account.get("account_identifier") or "",
            "instance_url": account.get("instance_url") or None,
            "auth_type": "api_key_app_key",
            "status": "unknown",
            "is_active": 1,
            "created_by": "service_discovery",
            "created_at": datetime.now(timezone.utc),
            "metadata": {"monitors": 45, "dashboards": 12, "alerts_active": 3},
        }
        suggestions = [_stamp(row, ident, parent_env=parent_env)]
        return {
            "source": "datadog",
            "source_account": account.get("account_name"),
            "discovered": suggestions,
        }

    async def discover_all_from_connected(self, connected_accounts: List[dict]) -> Dict[str, Any]:
        """Aggregate suggestions for each supported connected integration."""
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
