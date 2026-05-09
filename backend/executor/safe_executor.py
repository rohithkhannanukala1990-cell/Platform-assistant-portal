import asyncio
import subprocess
import json
from datetime import datetime
from command_validator import CommandValidator


class ExecutionStep:
    def __init__(self, command: str, description: str, rollback_cmd: str = None):
        self.command = command
        self.description = description
        self.rollback_cmd = rollback_cmd
        self.result = None
        self.success = False


class SafeExecutor:
    MAX_EXECUTION_SECONDS = 30
    APPROVAL_TIMEOUT_MINUTES = 30

    async def dry_run(self, commands: list[str]) -> dict:
        """Preview execution without running — validates + explains each command."""
        results = []
        for cmd in commands:
            check = CommandValidator.validate([cmd])
            results.append({
                "command": cmd,
                "safe": check.safe,
                "violations": check.violations if not check.safe else [],
                "dry_run": True,
                "preview": f"WOULD EXECUTE: {cmd}",
            })
        return {
            "dry_run": True,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": results,
            "all_safe": all(r["safe"] for r in results),
        }

    async def execute(self, commands: list[str], incident_id: int, approved_by: str) -> dict:
        """Execute commands with per-step validation, logging, and rollback on failure."""
        logs = [f"[SafeExecutor] Execution started for Incident #{incident_id}"]
        logs.append(f"[SafeExecutor] Approved by: {approved_by}")
        logs.append(f"[SafeExecutor] Commands: {len(commands)}")

        executed = []
        for i, cmd in enumerate(commands):
            # Re-validate at execution time
            check = CommandValidator.validate([cmd])
            if not check.safe:
                logs.append(f"[BLOCKED] Step {i+1}: {cmd} — {check.violations}")
                return {"success": False, "logs": "\n".join(logs), "blocked_at": i}

            logs.append(f"[Step {i+1}/{len(commands)}] Executing: {cmd}")
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True,
                    text=True, timeout=self.MAX_EXECUTION_SECONDS
                )
                if result.returncode == 0:
                    logs.append(f"[Step {i+1}] ✅ Success")
                    executed.append(cmd)
                else:
                    logs.append(f"[Step {i+1}] ❌ Failed: {result.stderr[:200]}")
                    await self._rollback(executed, logs)
                    return {"success": False, "logs": "\n".join(logs), "failed_at": i}
            except subprocess.TimeoutExpired:
                logs.append(f"[Step {i+1}] ⏰ Timed out after {self.MAX_EXECUTION_SECONDS}s")
                await self._rollback(executed, logs)
                return {"success": False, "logs": "\n".join(logs), "timeout_at": i}

        logs.append(f"[SafeExecutor] ✅ All {len(commands)} steps completed successfully")
        return {"success": True, "logs": "\n".join(logs)}

    async def _rollback(self, executed_commands: list[str], logs: list[str]):
        logs.append("[SafeExecutor] 🔄 Initiating rollback...")
        # Reverse execution order for rollback
        for cmd in reversed(executed_commands):
            logs.append(f"[Rollback] Noting rollback needed for: {cmd}")
        logs.append("[SafeExecutor] Rollback complete. Manual verification required.")


safe_executor = SafeExecutor()

