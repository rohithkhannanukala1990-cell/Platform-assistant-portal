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


class ToolExecutor:

    def requires_hitl(self, tool_id: str,
                      action: str,
                      environment: str) -> bool:
        if environment == "production":
            return action in HITL_REQUIRED_ACTIONS
        if environment in ["staging", "dr"]:
            return action in [
                "delete_resource",
                "apply_terraform",
                "deploy_to_production"
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
            "parameters": parameters,
            "requires_hitl": hitl,
            "status": "pending_approval"
                      if hitl else "executing",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        if not hitl:
            result = await self._run_action(
                tool_id, action, parameters)
            execution["result"] = result
            execution["status"] = "completed"
            execution["executed_at"] = (
                datetime.now(timezone.utc).isoformat())

        return execution

    async def _run_action(
        self, tool_id: str,
        action: str, parameters: Dict) -> Dict:
        return {
            "success": True,
            "tool": tool_id,
            "action": action,
            "output": f"[Simulated] {action} on "
                      f"{tool_id} completed.",
            "parameters": parameters
        }

    async def approve_execution(
        self, execution_id: str,
        approved_by: str) -> Dict:
        result = await self._run_action(
            "approved", "execute", {})
        return {
            "execution_id": execution_id,
            "status": "completed",
            "approved_by": approved_by,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "result": result
        }

    async def reject_execution(
        self, execution_id: str,
        rejected_by: str, reason: str = "") -> Dict:
        return {
            "execution_id": execution_id,
            "status": "rejected",
            "rejected_by": rejected_by,
            "reason": reason
        }


tool_executor = ToolExecutor()
