import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .environment_infer import apply_environment_to_account, requires_hitl_for_env


def _batch_env(credentials: dict | None) -> str | None:
    creds = credentials or {}
    for key in ("environment", "default_environment", "env"):
        val = creds.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return None


def _stamp(account: dict, credentials: dict | None, *hints: Any) -> dict:
    explicit = _batch_env(credentials)
    # Clear hard-coded env so inference can run unless batch override is set.
    account = dict(account)
    account.pop("environment", None)
    stamped = apply_environment_to_account(
        account,
        *hints,
        explicit=explicit,
        default="development",
    )
    stamped["requires_hitl"] = requires_hitl_for_env(stamped.get("environment"))
    return stamped


class CloudDiscovery:
    async def discover_aws(self, credentials: dict) -> Dict[str, Any]:
        regions = credentials.get("regions", ["us-east-1", "us-west-2", "eu-west-1"])
        account_id = credentials.get("account_id") or ""
        alias = credentials.get("account_alias") or credentials.get("account_name") or ""
        discovered: List[Dict[str, Any]] = []
        for region in regions:
            name = alias.strip() or f"AWS {str(region).upper()}"
            if alias.strip() and region:
                name = f"{alias.strip()} ({region})"
            row = {
                "id": str(uuid.uuid4()),
                "tool_id": "aws",
                "account_name": name,
                "region": str(region),
                "account_identifier": account_id or None,
                "instance_url": None,
                "auth_type": "iam_role",
                "status": "unknown",
                "is_active": 1,
                "created_by": "discovery",
                "created_at": datetime.now(timezone.utc),
                "discovered_services": ["ec2", "eks", "rds", "s3", "lambda"],
            }
            discovered.append(_stamp(row, credentials, alias, account_id, region))
        return {
            "provider": "aws",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_gcp(self, credentials: dict) -> Dict[str, Any]:
        project_id = credentials.get("project_id", "my-project")
        row = {
            "id": str(uuid.uuid4()),
            "tool_id": "gcp",
            "account_name": f"GCP {project_id}",
            "region": None,
            "account_identifier": project_id,
            "instance_url": None,
            "auth_type": "service_account",
            "status": "unknown",
            "is_active": 1,
            "created_by": "discovery",
            "created_at": datetime.now(timezone.utc),
            "discovered_services": ["gke", "gcs", "bigquery", "cloudsql"],
        }
        discovered = [_stamp(row, credentials, project_id)]
        return {
            "provider": "gcp",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_azure(self, credentials: dict) -> Dict[str, Any]:
        subscription_id = credentials.get("subscription_id", "")
        subscription_name = credentials.get("subscription_name") or credentials.get("account_name") or "Azure Subscription"
        row = {
            "id": str(uuid.uuid4()),
            "tool_id": "azure",
            "account_name": str(subscription_name),
            "region": None,
            "account_identifier": subscription_id or None,
            "instance_url": None,
            "auth_type": "client_secret",
            "status": "unknown",
            "is_active": 1,
            "created_by": "discovery",
            "created_at": datetime.now(timezone.utc),
            "discovered_services": ["aks", "blob", "sql", "functions"],
        }
        discovered = [_stamp(row, credentials, subscription_name, subscription_id)]
        return {
            "provider": "azure",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_github_org(self, credentials: dict) -> Dict[str, Any]:
        org = credentials.get("org_name", "")
        repos_count = credentials.get("repos_count", 45)
        row = {
            "id": str(uuid.uuid4()),
            "tool_id": "github",
            "account_name": f"GitHub {org}" if org else "GitHub Org",
            "region": None,
            "account_identifier": org or None,
            "instance_url": "https://github.com",
            "auth_type": "pat",
            "status": "unknown",
            "is_active": 1,
            "created_by": "discovery",
            "created_at": datetime.now(timezone.utc),
            "discovered_repos": repos_count,
        }
        discovered = [_stamp(row, credentials, org)]
        # GitHub org itself rarely needs HITL unless production-tagged.
        discovered[0]["requires_hitl"] = requires_hitl_for_env(discovered[0].get("environment"))
        return {
            "provider": "github",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }


cloud_discovery = CloudDiscovery()
