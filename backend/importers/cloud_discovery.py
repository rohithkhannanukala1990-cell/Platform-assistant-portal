import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


class CloudDiscovery:
    async def discover_aws(self, credentials: dict) -> Dict[str, Any]:
        regions = credentials.get("regions", ["us-east-1", "us-west-2", "eu-west-1"])
        discovered: List[Dict[str, Any]] = []
        for region in regions:
            discovered.append(
                {
                    "id": str(uuid.uuid4()),
                    "tool_id": "aws",
                    "account_name": f"AWS {str(region).upper()}",
                    "environment": "production",
                    "region": str(region),
                    "account_identifier": credentials.get("account_id") or None,
                    "instance_url": None,
                    "auth_type": "iam_role",
                    "requires_hitl": True,
                    "status": "unknown",
                    "is_active": 1,
                    "created_by": "discovery",
                    "created_at": datetime.now(timezone.utc),
                    "discovered_services": ["ec2", "eks", "rds", "s3", "lambda"],
                }
            )
        return {
            "provider": "aws",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_gcp(self, credentials: dict) -> Dict[str, Any]:
        project_id = credentials.get("project_id", "my-project")
        discovered = [
            {
                "id": str(uuid.uuid4()),
                "tool_id": "gcp",
                "account_name": f"GCP {project_id}",
                "environment": "production",
                "region": None,
                "account_identifier": project_id,
                "instance_url": None,
                "auth_type": "service_account",
                "requires_hitl": True,
                "status": "unknown",
                "is_active": 1,
                "created_by": "discovery",
                "created_at": datetime.now(timezone.utc),
                "discovered_services": ["gke", "gcs", "bigquery", "cloudsql"],
            }
        ]
        return {
            "provider": "gcp",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_azure(self, credentials: dict) -> Dict[str, Any]:
        subscription_id = credentials.get("subscription_id", "")
        discovered = [
            {
                "id": str(uuid.uuid4()),
                "tool_id": "azure",
                "account_name": "Azure Subscription",
                "environment": "production",
                "region": None,
                "account_identifier": subscription_id or None,
                "instance_url": None,
                "auth_type": "client_secret",
                "requires_hitl": True,
                "status": "unknown",
                "is_active": 1,
                "created_by": "discovery",
                "created_at": datetime.now(timezone.utc),
                "discovered_services": ["aks", "blob", "sql", "functions"],
            }
        ]
        return {
            "provider": "azure",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }

    async def discover_github_org(self, credentials: dict) -> Dict[str, Any]:
        org = credentials.get("org_name", "")
        repos_count = credentials.get("repos_count", 45)
        discovered = [
            {
                "id": str(uuid.uuid4()),
                "tool_id": "github",
                "account_name": f"GitHub {org}" if org else "GitHub Org",
                "environment": "production",
                "region": None,
                "account_identifier": org or None,
                "instance_url": "https://github.com",
                "auth_type": "pat",
                "requires_hitl": False,
                "status": "unknown",
                "is_active": 1,
                "created_by": "discovery",
                "created_at": datetime.now(timezone.utc),
                "discovered_repos": repos_count,
            }
        ]
        return {
            "provider": "github",
            "discovered_count": len(discovered),
            "accounts": discovered,
        }


cloud_discovery = CloudDiscovery()
