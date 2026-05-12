import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

EXPECTED_CSV_COLUMNS = [
    "tool_id",
    "account_name",
    "environment",
    "region",
    "account_identifier",
    "instance_url",
    "auth_type",
    "requires_hitl",
]


class CSVImporter:
    def parse_csv(self, content: str) -> Dict[str, Any]:
        reader = csv.DictReader(io.StringIO(content))
        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        for i, row in enumerate(reader):
            result = self.validate_row(row, i + 2)
            if result["valid"]:
                rows.append(result["data"])
            else:
                errors.append(result["error"])
        return {"rows": rows, "errors": errors}

    def validate_row(self, row: dict, line_num: int) -> dict:
        required = ["tool_id", "account_name", "environment", "auth_type"]
        for field in required:
            if not row.get(field, "").strip():
                return {
                    "valid": False,
                    "error": f"Line {line_num}: missing required field '{field}'",
                }
        valid_envs = ["local", "development", "test", "staging", "production", "dr"]
        if row["environment"].strip().lower() not in valid_envs:
            return {
                "valid": False,
                "error": f"Line {line_num}: invalid environment '{row['environment']}'",
            }
        return {
            "valid": True,
            "data": {
                "id": str(uuid.uuid4()),
                "tool_id": row["tool_id"].strip().lower(),
                "account_name": row["account_name"].strip(),
                "environment": row["environment"].strip().lower(),
                "region": row.get("region", "").strip() or None,
                "account_identifier": row.get("account_identifier", "").strip() or None,
                "instance_url": row.get("instance_url", "").strip() or None,
                "auth_type": (row.get("auth_type") or "api_key").strip(),
                "requires_hitl": row.get("requires_hitl", "0").strip().lower()
                in ("1", "true", "yes"),
                "status": "unknown",
                "is_active": 1,
                "created_by": "import",
                "created_at": datetime.now(timezone.utc),
            },
        }

    def generate_template(self) -> str:
        header = ",".join(EXPECTED_CSV_COLUMNS)
        example_rows = [
            "aws,AWS Production US-East,production,us-east-1,123456789012,,iam_role,1",
            "github,GitHub Org Main,production,,my-org,https://github.com,pat,0",
            "jira,Jira Engineering,staging,,eng@company.com,https://company.atlassian.net,api_token,0",
            "datadog,Datadog Prod,production,us1,,,api_key_app_key,1",
            "kubernetes,K8s Production,production,us-east-1,prod-cluster,,kubeconfig,1",
        ]
        return header + "\n" + "\n".join(example_rows)


csv_importer = CSVImporter()
