import asyncio
import subprocess
import shlex
import json
from datetime import datetime
from ..command_validator import CommandValidator


def _default_context() -> dict:
    """Conservative context for legacy callers that do not pass one.

    Uses the process ENV as environment so production deployments stay
    fail-closed even when a call site predates Phase G1.
    """
    import os

    return {
        "role": "User",
        "environment": (os.getenv("ENV") or "development").strip().lower(),
        "tool": "shell",
        "tenant_id": None,
        "approved": False,
    }


def _audit_policy_event(event_type: str, context: dict, command: str, reasons: list[str]) -> None:
    try:
        from ..auth import write_audit

        write_audit(
            actor=str(context.get("approved_by") or context.get("user_id") or "system"),
            actor_role=str(context.get("role") or "User"),
            event_type=event_type,
            resource=f"incident:{context.get('incident_id') or 0}",
            detail=f"{command[:200]} — {'; '.join(reasons)[:300]}",
        )
    except Exception:
        pass  # audit must never break execution handling


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

    async def dry_run(self, commands: list[str], context: dict | None = None) -> dict:
        """Preview execution without running — validates + explains each command."""
        ctx = {**_default_context(), **(context or {})}
        results = []
        for cmd in commands:
            check = CommandValidator.validate_with_context(
                [cmd],
                role=str(ctx.get("role") or "User"),
                environment=str(ctx.get("environment") or "development"),
                tool=str(ctx.get("tool") or "shell"),
                tenant_id=ctx.get("tenant_id"),
            )
            decision = check.decision
            results.append({
                "command": cmd,
                "safe": check.safe,
                "effect": check.effect,
                "requires_approval": check.requires_approval,
                "violations": check.violations if not check.safe else [],
                "reasons": list(decision.reasons) if decision else [],
                "matched_rule_ids": list(decision.matched_rule_ids) if decision else [],
                "dry_run": True,
                "preview": f"WOULD EXECUTE: {cmd}",
            })
        return {
            "dry_run": True,
            "timestamp": datetime.utcnow().isoformat(),
            "steps": results,
            "all_safe": all(r["safe"] for r in results),
            "any_requires_approval": any(r["requires_approval"] for r in results),
        }

    async def execute(
        self,
        commands: list[str],
        incident_id: int,
        approved_by: str,
        context: dict | None = None,
    ) -> dict:
        """Execute commands with per-step policy evaluation, logging, and rollback.

        ``context`` keys: role, environment, tool, tenant_id, approved_by,
        incident_id, approved (bool — set True only after HITL approval).
        """
        ctx = {**_default_context(), **(context or {})}
        ctx.setdefault("approved_by", approved_by)
        ctx.setdefault("incident_id", incident_id)
        approved = bool(ctx.get("approved"))

        logs = [f"[SafeExecutor] Execution started for Incident #{incident_id}"]
        logs.append(f"[SafeExecutor] Approved by: {approved_by}")
        logs.append(f"[SafeExecutor] Commands: {len(commands)}")
        logs.append(
            f"[SafeExecutor] Policy context: role={ctx.get('role')} "
            f"env={ctx.get('environment')} tool={ctx.get('tool')} approved={approved}"
        )

        executed = []
        for i, cmd in enumerate(commands):
            # Re-evaluate policy at execution time (per step)
            check = CommandValidator.validate_with_context(
                [cmd],
                role=str(ctx.get("role") or "User"),
                environment=str(ctx.get("environment") or "development"),
                tool=str(ctx.get("tool") or "shell"),
                tenant_id=ctx.get("tenant_id"),
            )
            decision = check.decision
            reasons = list(decision.reasons) if decision else list(check.violations)

            if not check.safe:
                logs.append(f"[BLOCKED] Step {i+1}: {cmd} — policy deny: {reasons}")
                _audit_policy_event("command_policy_denied", ctx, cmd, reasons)
                return {
                    "success": False,
                    "logs": "\n".join(logs),
                    "blocked_at": i,
                    "policy_effect": "deny",
                    "policy_reasons": reasons,
                }

            if check.requires_approval and not approved:
                logs.append(
                    f"[REFUSED] Step {i+1}: {cmd} — requires approval and no approval flag set"
                )
                _audit_policy_event("command_policy_approval_required", ctx, cmd, reasons)
                return {
                    "success": False,
                    "logs": "\n".join(logs),
                    "blocked_at": i,
                    "policy_effect": "require_approval",
                    "policy_reasons": reasons,
                    "requires_approval": True,
                }

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
