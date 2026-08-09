"""Terraform plan/apply with frozen plan artifact (no re-plan after approval)."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable


class TerraformStateLocked(RuntimeError):
    """Raised when terraform state is locked — apply must not consume approval."""

    def __init__(self, holder: str, message: str | None = None):
        self.holder = holder or "unknown"
        super().__init__(
            message
            or f"Terraform state is locked by {self.holder}. Retry when the lock is released."
        )


def parse_plan_json(plan: dict[str, Any] | None) -> dict[str, Any]:
    """Parse `terraform show -json` output into a structured resource diff."""
    plan = plan if isinstance(plan, dict) else {}
    resource_changes = plan.get("resource_changes") or []
    to_add: list[str] = []
    to_change: list[str] = []
    to_destroy: list[str] = []
    for rc in resource_changes:
        addr = str(rc.get("address") or "")
        actions = list((rc.get("change") or {}).get("actions") or [])
        if not addr:
            continue
        if actions == ["create"] or "create" in actions and "delete" not in actions:
            to_add.append(addr)
        elif "delete" in actions and "create" not in actions:
            to_destroy.append(addr)
        elif actions == ["delete", "create"] or actions == ["create", "delete"]:
            to_change.append(addr)
            to_destroy.append(addr)  # replace still destroys current
        elif "update" in actions or "replace" in str(actions):
            to_change.append(addr)
        elif "delete" in actions:
            to_destroy.append(addr)
        elif "create" in actions:
            to_add.append(addr)
        else:
            to_change.append(addr)
    # Unique destroy addresses for destroy_count
    destroy_unique = list(dict.fromkeys(to_destroy))
    return {
        "resources_to_add": list(dict.fromkeys(to_add)),
        "resources_to_change": list(dict.fromkeys(to_change)),
        "resources_to_destroy": destroy_unique,
        "destroy_count": len(destroy_unique),
    }


def _run_tf(
    args: list[str],
    *,
    cwd: str,
    env: dict[str, str] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    merged = {**os.environ, **(env or {})}
    return subprocess.run(
        args,
        cwd=cwd,
        env=merged,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check_state_lock(
    working_directory: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Return {locked: bool, holder: str|None, detail: str}."""
    run = runner or _run_tf
    # `terraform force-unlock -help` won't help; use state list / plan with lock info.
    # Prefer reading .terraform.tfstate.lock.info if present; else probe via apply -lock-timeout=0 dry.
    lock_info = Path(working_directory) / ".terraform.tfstate.lock.info"
    if lock_info.is_file():
        try:
            data = json.loads(lock_info.read_text(encoding="utf-8"))
            holder = (
                data.get("Who")
                or data.get("who")
                or data.get("ID")
                or data.get("ID")
                or "unknown"
            )
            return {"locked": True, "holder": str(holder), "detail": json.dumps(data)[:500]}
        except Exception as exc:
            return {"locked": True, "holder": "unknown", "detail": str(exc)[:200]}

    # Probe: terraform plan -lock=true -lock-timeout=0s -refresh=false -input=false
    # with no changes expected — if lock held, stderr mentions Lock Info / Locked
    proc = run(
        ["terraform", "plan", "-lock=true", "-lock-timeout=0s", "-refresh=false", "-input=false", "-detailed-exitcode"],
        cwd=working_directory,
        timeout=60,
    )
    combined = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if re.search(r"Error acquiring the state lock|Lock Info:|state locked", combined, re.I):
        holder = "unknown"
        m = re.search(r"Who:\s*(.+)", combined)
        if m:
            holder = m.group(1).strip()
        else:
            m2 = re.search(r"ID:\s*(\S+)", combined)
            if m2:
                holder = m2.group(1).strip()
        return {"locked": True, "holder": holder, "detail": combined[:800]}
    return {"locked": False, "holder": None, "detail": ""}


async def run_terraform_plan(
    *,
    working_directory: str,
    workspace: str = "default",
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Run terraform plan -out=tfplan and capture binary + JSON + text + parsed diff."""
    run = runner or _run_tf
    workdir = working_directory

    def _sync() -> dict[str, Any]:
        # Select workspace (create if missing)
        ws = run(["terraform", "workspace", "select", workspace], cwd=workdir, timeout=60)
        if ws.returncode != 0:
            run(["terraform", "workspace", "new", workspace], cwd=workdir, timeout=60)
            run(["terraform", "workspace", "select", workspace], cwd=workdir, timeout=60)

        plan_path = str(Path(workdir) / "tfplan")
        plan_proc = run(
            ["terraform", "plan", "-out=tfplan", "-input=false", "-no-color"],
            cwd=workdir,
            timeout=600,
        )
        plan_text = (plan_proc.stdout or "") + ("\n" + plan_proc.stderr if plan_proc.stderr else "")
        if plan_proc.returncode not in (0, 2):
            return {
                "ok": False,
                "error": plan_text[:2000] or f"terraform plan exit {plan_proc.returncode}",
                "plan_text": plan_text,
            }

        show_json = run(
            ["terraform", "show", "-json", "tfplan"],
            cwd=workdir,
            timeout=120,
        )
        plan_json: dict[str, Any] = {}
        try:
            plan_json = json.loads(show_json.stdout or "{}")
        except Exception:
            plan_json = {}

        show_text = run(
            ["terraform", "show", "-no-color", "tfplan"],
            cwd=workdir,
            timeout=120,
        )
        human = show_text.stdout or plan_text

        plan_bytes = b""
        p = Path(plan_path)
        if p.is_file():
            plan_bytes = p.read_bytes()

        diff = parse_plan_json(plan_json)
        return {
            "ok": True,
            "plan_b64": base64.b64encode(plan_bytes).decode("ascii"),
            "plan_text": human[:50000],
            "plan_json": plan_json,
            "diff": diff,
            "workspace": workspace,
            "working_directory": workdir,
            "destroy_count": diff["destroy_count"],
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def apply_stored_plan(
    *,
    working_directory: str,
    plan_b64: str,
    workspace: str = "default",
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    lock_checker: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Write frozen plan bytes to disk and `terraform apply tfplan` — never re-plan."""
    run = runner or _run_tf
    check = lock_checker or check_state_lock

    def _sync() -> dict[str, Any]:
        lock = check(working_directory, runner=run)
        if lock.get("locked"):
            raise TerraformStateLocked(str(lock.get("holder") or "unknown"))

        plan_bytes = base64.b64decode(plan_b64.encode("ascii"))
        plan_path = Path(working_directory) / "tfplan"
        plan_path.write_bytes(plan_bytes)

        # Ensure workspace
        run(["terraform", "workspace", "select", workspace], cwd=working_directory, timeout=60)

        apply_proc = run(
            ["terraform", "apply", "-input=false", "-auto-approve", "-no-color", "tfplan"],
            cwd=working_directory,
            timeout=900,
        )
        out = (apply_proc.stdout or "") + ("\n" + apply_proc.stderr if apply_proc.stderr else "")
        # Detect lock errors during apply
        if re.search(r"Error acquiring the state lock|state locked", out, re.I):
            holder = "unknown"
            m = re.search(r"Who:\s*(.+)", out)
            if m:
                holder = m.group(1).strip()
            raise TerraformStateLocked(holder, out[:500])

        ok = apply_proc.returncode == 0
        return {
            "ok": ok,
            "output": out[:20000],
            "url": None,
            "error": None if ok else out[:1000],
        }

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)
