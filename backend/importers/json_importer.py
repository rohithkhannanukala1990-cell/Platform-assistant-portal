import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List


class JSONImporter:
    def parse_json(self, content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return {"rows": [], "errors": [f"Invalid JSON: {str(e)}"]}

        if isinstance(data, list):
            accounts = data
        elif isinstance(data, dict) and "accounts" in data:
            accounts = data["accounts"]
        elif isinstance(data, dict) and "tools" in data:
            accounts = []
            for tool_id, tool_accounts in data["tools"].items():
                for acc in tool_accounts:
                    acc = dict(acc)
                    acc["tool_id"] = tool_id
                    accounts.append(acc)
        else:
            return {
                "rows": [],
                "errors": ["JSON must be array or object with 'accounts' or 'tools' key"],
            }

        rows: List[Dict[str, Any]] = []
        errors: List[str] = []
        for i, account in enumerate(accounts):
            result = self.validate_account(account, i + 1)
            if result["valid"]:
                rows.append(result["data"])
            else:
                errors.append(result["error"])
        return {"rows": rows, "errors": errors}

    def validate_account(self, account: dict, index: int) -> dict:
        required = ["tool_id", "account_name", "environment", "auth_type"]
        for field in required:
            val = account.get(field, "")
            if val is None or (isinstance(val, str) and not val.strip()):
                return {
                    "valid": False,
                    "error": f"Account {index}: missing required field '{field}'",
                }
        valid_envs = ["local", "development", "test", "staging", "production", "dr"]
        env = str(account["environment"]).strip().lower()
        if env not in valid_envs:
            return {
                "valid": False,
                "error": f"Account {index}: invalid environment '{account['environment']}'",
            }
        rh = account.get("requires_hitl", False)
        if isinstance(rh, str):
            requires_hitl = rh.strip().lower() in ("1", "true", "yes")
        else:
            requires_hitl = bool(rh)
        return {
            "valid": True,
            "data": {
                "id": str(uuid.uuid4()),
                "tool_id": str(account["tool_id"]).strip().lower(),
                "account_name": str(account["account_name"]).strip(),
                "environment": env,
                "region": (str(account.get("region") or "").strip() or None),
                "account_identifier": (str(account.get("account_identifier") or "").strip() or None),
                "instance_url": (str(account.get("instance_url") or "").strip() or None),
                "auth_type": str(account.get("auth_type") or "api_key").strip(),
                "requires_hitl": requires_hitl,
                "status": "unknown",
                "is_active": 1,
                "created_by": "import",
                "created_at": datetime.now(timezone.utc),
            },
        }


json_importer = JSONImporter()
