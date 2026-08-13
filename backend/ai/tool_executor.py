import uuid
from datetime import datetime, timezone
from typing import Dict

HITL_REQUIRED_ACTIONS = [
    "restart_service",
    "delete_resource",
    "scale_deployment",
    "apply_terraform",
    "merge_pull_request",
    "deploy_to_production",
    "rotate_secrets",
    "modify_iam_policy"
]

# Any operation verb that mutates state; in production these always need HITL.
_PRODUCTION_MUTATING_PREFIXES = (
    "restart",
    "delete",
    "scale",
    "apply",
    "merge",
    "deploy",
    "rotate",
    "modify",
    "create",
    "update",
    "terminate",
    "drain",
    "failover",
)

# Pending HITL executions keyed by execution id (in-memory; lost on restart).
_pending_executions: dict[str, dict] = {}


class ToolExecutor:

    def requires_hitl(self, tool_id: str,
                      action: str,
                      environment: str) -> bool:
        action_norm = (action or "").strip().lower()
        if environment == "production":
            if action_norm in HITL_REQUIRED_ACTIONS:
                return True
            # Production deployments, secret rotation, and infra changes must
            # always be approved by a human, even for unlisted action names.
            return action_norm.startswith(_PRODUCTION_MUTATING_PREFIXES)
        if environment in ["staging", "dr"]:
            return action_norm in [
                "delete_resource",
                "apply_terraform",
                "deploy_to_production",
                "rotate_secrets",
            ]
        return False

    async def execute(
        self,
        tool_id: str,
        action: str,
        parameters: Dict,
        environment: str,
        conversation_id: str,
        message_id: str = None
    ) -> Dict:
        exec_id = str(uuid.uuid4())
        hitl = self.requires_hitl(
            tool_id, action, environment)

        execution = {
            "id": exec_id,
            "conversation_id": conversation_id,
            "message_id": message_id,
            "tool_id": tool_id,
            "action": action,
            "parameters": parameters or {},
            "requires_hitl": hitl,
            "status": "pending_approval"
                      if hitl else "executing",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "executed_at": None,
            "result": None,
        }

        if hitl:
            _pending_executions[exec_id] = {
                "tool_id": tool_id,
                "action": action,
                "parameters": parameters or {},
                "environment": environment,
                "conversation_id": conversation_id,
                "created_at": execution["created_at"],
            }
            return execution

        try:
            result = await self._run_action(
                tool_id, action, parameters)
            execution["result"] = result
            execution["status"] = (
                "completed"
                if result.get("success", True)
                else "error"
            )
            execution["executed_at"] = (
                datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            execution["status"] = "error"
            execution["executed_at"] = (
                datetime.now(timezone.utc).isoformat())
            execution["result"] = {
                "success": False,
                "output": str(exc),
                "metadata": {
                    "tool": tool_id,
                    "action": action,
                    "error_type": type(exc).__name__,
                },
            }

        return execution

    async def _run_action(
        self, tool_id: str,
        action: str, parameters: Dict) -> Dict:
        params = parameters or {}
        return {
            "success": True,
            "output": f"[Simulated] {action} on "
                      f"{tool_id} completed.",
            "metadata": {
                "tool": tool_id,
                "action": action,
                "resource": params.get("resource"),
                "identifier": params.get("identifier"),
                "environment": params.get("environment"),
                "parameters": params,
            },
        }

    async def approve_execution(
        self, execution_id: str,
        approved_by: str) -> Dict:
        pending = _pending_executions.pop(execution_id, None)
        if not pending:
            return {
                "execution_id": execution_id,
                "status": "not_found",
                "error": f"No pending execution found for id={execution_id}",
            }
        result = await self._run_action(
            pending["tool_id"],
            pending["action"],
            pending.get("parameters") or {},
        )
        return {
            "execution_id": execution_id,
            "status": "completed",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "result": result,
        }

    async def reject_execution(
        self, execution_id: str,
        rejected_by: str, reason: str = "") -> Dict:
        _pending_executions.pop(execution_id, None)
        return {
            "execution_id": execution_id,
            "status": "rejected",
            "rejected_by": rejected_by,
            "reason": reason
        }


tool_executor = ToolExecutor()
