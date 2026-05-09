import asyncio
import subprocess
import shlex
import json
from datetime import datetime
from ..command_validator import CommandValidator


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
                    shlex.split(cmd), shell=False, capture_output=True,
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
        for cmd in reversed(executed_commands):
            rollback_cmd = self._infer_rollback(cmd)
            if rollback_cmd:
                logs.append(f"[Rollback] Executing: {rollback_cmd}")
                try:
                    result = subprocess.run(
                        shlex.split(rollback_cmd), shell=False,
                        capture_output=True, text=True,
                        timeout=self.MAX_EXECUTION_SECONDS
                    )
                    if result.returncode == 0:
                        logs.append(f"[Rollback] ✅ Success: {rollback_cmd}")
                    else:
                        logs.append(f"[Rollback] ❌ Failed: {result.stderr[:200]}")
                except Exception as exc:
                    logs.append(f"[Rollback] ⚠️ Error: {exc}")
            else:
                logs.append(f"[Rollback] ⚠️ No rollback known for: {cmd} — manual fix required")
        logs.append("[SafeExecutor] Rollback complete. Verify system state.")

    def _infer_rollback(self, cmd: str) -> str | None:
        """Map known forward commands to their rollback equivalents."""
        if "kubectl rollout restart" in cmd:
            return cmd.replace("rollout restart", "rollout undo")
        if "kubectl scale" in cmd and "--replicas=0" in cmd:
            return cmd.replace("--replicas=0", "--replicas=1")
        if "argocd app sync" in cmd:
            return cmd.replace("sync", "rollback")
        return None


safe_executor = SafeExecutor()

