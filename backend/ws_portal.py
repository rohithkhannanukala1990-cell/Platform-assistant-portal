"""In-memory WebSocket hub for portal push and agent-run streaming."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from .auth import User, decode_token
from .context import PlatformContext
from .database import AgentRun, engine

_user_clients: Dict[str, List[WebSocket]] = {}
_run_watchers: Dict[str, List[WebSocket]] = {}

TERMINAL_STATUSES = frozenset({"success", "failed", "pending_approval"})
POLL_INTERVAL_S = 1.5
MAX_WATCH_S = 120.0
WS_AUTH_TIMEOUT_S = 5.0

router = APIRouter(tags=["websocket"])


def _authenticate_ws_token(token: str) -> Optional[User]:
    """Validate JWT using the same logic as get_current_user."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        username = str(payload.get("sub"))
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == username)).first()
            if user and user.is_active:
                return user
    except Exception:
        return None
    return None


async def _accept_and_read_token(websocket: WebSocket) -> Optional[str]:
    """Accept the socket, then require `{token}` in the first client message.

    Tokens must not appear in the WebSocket URL (proxy/access logs).
    """
    await websocket.accept()
    try:
        auth_msg = await asyncio.wait_for(
            websocket.receive_text(), timeout=WS_AUTH_TIMEOUT_S
        )
        data = json.loads(auth_msg)
        if isinstance(data, dict):
            sid = data.get("session_id")
            if sid:
                try:
                    websocket.state.terminal_session_id = str(sid)
                except Exception:
                    pass
            return str(data.get("token") or "")
    except Exception:
        try:
            await websocket.send_json({"type": "error", "message": "auth_required"})
            await websocket.close(code=1008)
        except Exception:
            pass
        return None
    try:
        await websocket.send_json({"type": "error", "message": "auth_required"})
        await websocket.close(code=1008)
    except Exception:
        pass
    return None


async def _reject_unauthorized(websocket: WebSocket) -> None:
    try:
        await websocket.send_json({"type": "error", "message": "unauthorized"})
        await websocket.close(code=1008)
    except Exception:
        pass


def _fetch_run_sync(run_id: str) -> Optional[AgentRun]:
    with Session(engine) as session:
        return session.get(AgentRun, run_id)


async def ws_broadcast(
    run_id: str,
    agent: str,
    status: str,
    summary: str = "",
    timestamp: str | None = None,
) -> None:
    """Push agent-run status to subscribers and portal clients."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    payload = {
        "type": "status",
        "run_id": run_id,
        "agent": agent,
        "status": status,
        "summary": summary,
        "timestamp": ts,
    }
    dead: list[WebSocket] = []
    for ws in list(_run_watchers.get(run_id, [])):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _run_watchers[run_id].remove(ws)
        except (ValueError, KeyError):
            pass
    await broadcast_json(payload)


async def accept_portal_connection(websocket: WebSocket) -> None:
    """Portal push channel. Identity comes from the JWT, never from the client."""
    token = await _accept_and_read_token(websocket)
    if token is None:
        return
    user = _authenticate_ws_token(token)
    if not user:
        await _reject_unauthorized(websocket)
        return

    user_id = user.username
    _user_clients.setdefault(user_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        try:
            _user_clients[user_id].remove(websocket)
        except (ValueError, KeyError):
            pass


async def accept_agent_run_connection(websocket: WebSocket, run_id: str) -> None:
    token = await _accept_and_read_token(websocket)
    if token is None:
        return
    user = _authenticate_ws_token(token)
    if not user:
        await _reject_unauthorized(websocket)
        return

    _run_watchers.setdefault(run_id, []).append(websocket)
    loop = asyncio.get_event_loop()
    started = time.monotonic()
    last_sent: Optional[str] = None

    try:
        while time.monotonic() - started < MAX_WATCH_S:
            row = await loop.run_in_executor(None, _fetch_run_sync, run_id)
            if row:
                payload = {
                    "type": "status",
                    "run_id": run_id,
                    "agent": row.agent,
                    "status": row.status,
                    "summary": row.summary,
                    "timestamp": (
                        row.updated_at.isoformat()
                        if row.updated_at
                        else row.created_at.isoformat() if row.created_at else ""
                    ),
                }
                sig = f"{row.status}|{row.summary}"
                if sig != last_sent:
                    await websocket.send_json(payload)
                    last_sent = sig
                if row.status in TERMINAL_STATUSES:
                    break
            await asyncio.sleep(POLL_INTERVAL_S)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            _run_watchers[run_id].remove(websocket)
        except (ValueError, KeyError):
            pass
        try:
            await websocket.close()
        except Exception:
            pass


@router.websocket("/ws/agent-run/{run_id}")
async def agent_run_ws(websocket: WebSocket, run_id: str):
    await accept_agent_run_connection(websocket, run_id)


async def broadcast_json(payload: dict) -> None:
    """Fan-out JSON to ALL connected portal clients."""
    dead: list = []
    for uid, sockets in list(_user_clients.items()):
        for ws in list(sockets):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append((uid, ws))
    for uid, ws in dead:
        try:
            _user_clients[uid].remove(ws)
        except (ValueError, KeyError):
            pass


async def send_to_user(user_id: str, payload: dict) -> None:
    """Send JSON to a specific user only."""
    for ws in list(_user_clients.get(user_id, [])):
        try:
            await ws.send_json(payload)
        except Exception:
            pass


BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"DROP\s+TABLE",
    r"DROP\s+DATABASE",
    r"kubectl\s+delete\s+namespace",
    r"mkfs\.",
    r"dd\s+if=",
    r">\s+/dev/sd",
    r"chmod\s+777\s+/",
    r"shutdown",
    r"reboot",
    r"halt",
]


def _is_blocked(command: str) -> bool:
    import re

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True
    return False


def _prompt(cwd: str) -> str:
    return f"{cwd} $ "


async def _send(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_json(payload)


async def _send_output(websocket: WebSocket, data: str) -> None:
    await websocket.send_json({"type": "output", "data": data})


async def _execute_shell_command(
    websocket: WebSocket,
    *,
    command: str,
    user: User,
    cwd: str,
    approved: bool,
) -> None:
    from .executor.safe_executor import safe_executor

    try:
        # cwd is tracked for UX/completions; SafeExecutor still uses shell=False.
        result = await safe_executor.execute(
            [command],
            incident_id=0,
            approved_by=user.username,
            context={
                "role": user.role,
                "environment": PlatformContext.current_env(),
                "tool": "shell",
                "tenant_id": getattr(user, "tenant_id", None),
                "approved": bool(approved),
                "cwd": cwd,
            },
        )
        logs = result.get("logs") or ""
        success = result.get("success", False)
        status = "" if success else "\r\n[non-zero exit]"
        await _send_output(websocket, f"\r\n{logs}{status}\r\n")
    except Exception as exc:
        await _send_output(websocket, f"\r\nError: {exc}\r\n")


async def _handle_at_command(
    websocket: WebSocket,
    *,
    command: str,
    user: User,
    tenant_id: str,
) -> None:
    from .pipeline.orchestrator import run_agent_for_workflow
    from .services.terminal_service import (
        format_agent_help,
        format_agent_list,
        grounding_ansi,
        recent_runs_for_user,
        resolve_agent_alias,
    )

    body = command[1:].strip()
    alias, _, task = body.partition(" ")
    alias = alias.strip().lower()
    task = task.strip()

    if alias in {"", "help"}:
        await _send_output(websocket, f"\r\n{format_agent_help()}\r\n")
        return
    if alias == "agents":
        await _send_output(websocket, f"\r\n{format_agent_list()}\r\n")
        return
    if alias == "runs":
        rows = recent_runs_for_user(tenant_id=tenant_id, username=user.username, limit=10)
        if not rows:
            await _send_output(websocket, "\r\nNo recent agent runs.\r\n")
            return
        lines = ["Recent agent runs:"]
        for r in rows:
            lines.append(
                f"  {r['created_at'] or '?'}  {r['agent']}  [{r['status']}]  {(r['summary'] or '')[:80]}"
            )
        await _send_output(websocket, "\r\n" + "\r\n".join(lines) + "\r\n")
        return

    agent_name = resolve_agent_alias(alias)
    if not agent_name:
        await _send_output(
            websocket,
            f"\r\nUnknown agent '@{alias}'. Try @agents for the list.\r\n",
        )
        return
    if not task:
        await _send_output(
            websocket,
            f"\r\nUsage: @{alias} <task>\r\n",
        )
        return

    ctx = PlatformContext(
        user_id=user.username,
        user_role=user.role or "User",
        tenant_id=tenant_id,
        workspace_id=getattr(user, "workspace_id", None) or "",
        environment=PlatformContext.current_env() or "development",
    )
    await _send_output(websocket, f"\r\n\x1b[36m▶ Running {agent_name}…\x1b[0m\r\n")
    result = await run_agent_for_workflow(agent_name, {"task": task}, ctx)
    badge = grounding_ansi(result.grounding)
    await _send_output(
        websocket,
        f"{badge} {result.agent} — {result.status}\r\n{result.summary}\r\n",
    )
    if (result.grounding or "").lower() == "none":
        hint = (result.details or {}).get("connect_hint") or "Connect the tool in Tool Registry, then retry."
        await _send_output(websocket, f"\x1b[31m{hint}\x1b[0m\r\n")
    for ev in (result.evidence or [])[:8]:
        if not isinstance(ev, dict):
            continue
        title = ev.get("title") or "evidence"
        url = ev.get("url") or ""
        line = f"  • {title}"
        if url:
            line += f"  {url}"
        await _send_output(websocket, line + "\r\n")
    if result.status == "pending_approval" or result.requires_approval:
        await _send_output(
            websocket,
            "\x1b[33mAgent proposed write actions — approve in Approvals queue.\x1b[0m\r\n",
        )


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    import os
    import uuid as uuid_mod

    from .services.terminal_service import (
        complete_options,
        create_terminal_approval,
        get_terminal_approval,
        load_history,
        load_session_state,
        mark_approval_status,
        publish_approval_decision,
        register_decision_waiter,
        save_session_state,
        store_history,
    )

    raw_token = await _accept_and_read_token(websocket)
    if raw_token is None:
        return
    # First message may be plain token string from helper, or we already parsed token.
    # _accept_and_read_token returns token string only.
    user = _authenticate_ws_token(raw_token)
    if not user:
        await _reject_unauthorized(websocket)
        return

    tenant_id = getattr(user, "tenant_id", None) or "default"
    session_id = str(uuid_mod.uuid4())
    cwd = os.getcwd()
    scrollback = ""
    pending_approval_id: str | None = None

    # Client may have sent session_id inside the auth JSON — re-read via a race-safe approach:
    # Auth helper only returns token. Support resume via a follow-up is awkward;
    # instead parse session from a second optional field by accepting auth in-line below.
    # For resume: clients send {token, session_id} — enhance auth reader locally.
    # If token auth already consumed the message, session_id was lost. Fix auth path:

    # Re-open: monkey-patch — we need session_id from first message.
    # The accept helper discarded other fields. Store last auth blob on websocket.state.
    resume_id = getattr(websocket.state, "terminal_session_id", None) or ""
    if resume_id:
        prev = load_session_state(str(resume_id))
        if prev:
            session_id = str(resume_id)
            cwd = prev.get("cwd") or cwd
            scrollback = prev.get("scrollback") or ""

    await _send(
        websocket,
        {
            "type": "session",
            "session_id": session_id,
            "cwd": cwd,
            "scrollback": scrollback,
        },
    )
    history = load_history(tenant_id=tenant_id, username=user.username, limit=100)
    await _send(websocket, {"type": "history", "data": history})
    banner = (
        f"Platform Assistant Terminal\r\n"
        f"User: {user.username}\r\n"
        f"Type 'help' or '@help' for commands.\r\n"
        f"{_prompt(cwd)}"
    )
    if not scrollback:
        await _send_output(websocket, banner)
    else:
        await _send_output(websocket, _prompt(cwd))

    IDLE_WARN_S = 240.0
    IDLE_KILL_S = 300.0
    idle_warned = False
    decision_event: asyncio.Event | None = None
    decision_payload: dict | None = None
    unregister_waiter = None

    def _on_decision(payload: dict) -> None:
        nonlocal decision_payload, decision_event
        decision_payload = payload
        if decision_event is not None:
            decision_event.set()

    async def _wait_message(timeout: float) -> str | None:
        try:
            return await asyncio.wait_for(websocket.receive_text(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except WebSocketDisconnect:
            raise

    try:
        while True:
            timeout = IDLE_WARN_S if not idle_warned else (IDLE_KILL_S - IDLE_WARN_S)
            # Also wait for approval decisions while pending
            if pending_approval_id and decision_event is not None:
                msg_task = asyncio.create_task(websocket.receive_text())
                wait_task = asyncio.create_task(decision_event.wait())
                done, pending = await asyncio.wait(
                    {msg_task, wait_task},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    for t in pending:
                        t.cancel()
                    msg = None
                elif wait_task in done and decision_event.is_set():
                    msg_task.cancel()
                    # Handle decision
                    payload = decision_payload or {}
                    decision_event.clear()
                    decision_payload = None
                    aid = str(payload.get("approval_id") or "")
                    if aid == pending_approval_id:
                        if payload.get("type") == "approval_granted":
                            await _send(
                                websocket,
                                {"type": "approval_granted", "approval_id": aid},
                            )
                            row = get_terminal_approval(aid, tenant_id)
                            # CRITICAL: execute exact command from DB record
                            if row and row.command:
                                await _execute_shell_command(
                                    websocket,
                                    command=row.command,
                                    user=user,
                                    cwd=cwd,
                                    approved=True,
                                )
                                store_history(
                                    tenant_id=tenant_id,
                                    username=user.username,
                                    command=row.command,
                                )
                            pending_approval_id = None
                            if unregister_waiter:
                                unregister_waiter()
                                unregister_waiter = None
                            await _send_output(websocket, _prompt(cwd))
                        elif payload.get("type") == "approval_denied":
                            await _send(
                                websocket,
                                {
                                    "type": "approval_denied",
                                    "approval_id": aid,
                                    "reason": payload.get("reason") or "denied",
                                },
                            )
                            pending_approval_id = None
                            if unregister_waiter:
                                unregister_waiter()
                                unregister_waiter = None
                            await _send_output(websocket, _prompt(cwd))
                    continue
                else:
                    wait_task.cancel()
                    try:
                        msg = msg_task.result()
                    except Exception:
                        break
            else:
                msg = await _wait_message(timeout)

            if msg is None:
                if not idle_warned:
                    idle_warned = True
                    await _send(websocket, {"type": "idle_warn"})
                    continue
                await _send_output(websocket, "\r\nSession timed out (5 min idle).\r\n")
                break

            idle_warned = False

            # JSON control messages
            if msg.startswith("{"):
                try:
                    data = json.loads(msg)
                except Exception:
                    data = None
                if isinstance(data, dict):
                    if "token" in data:
                        continue
                    mtype = data.get("type")
                    if mtype == "activity":
                        continue
                    if mtype == "complete":
                        opts = complete_options(
                            str(data.get("partial") or ""),
                            tenant_id=tenant_id,
                            cwd=cwd,
                        )
                        await _send(websocket, {"type": "completions", "options": opts})
                        continue
                    if mtype == "cancel_approval":
                        aid = str(data.get("approval_id") or pending_approval_id or "")
                        if aid:
                            mark_approval_status(
                                aid,
                                status="cancelled",
                                decided_by=user.username,
                                reason="Cancelled from terminal",
                            )
                            publish_approval_decision(
                                {
                                    "type": "approval_denied",
                                    "approval_id": aid,
                                    "reason": "Cancelled from terminal",
                                }
                            )
                            pending_approval_id = None
                            if unregister_waiter:
                                unregister_waiter()
                                unregister_waiter = None
                        await _send_output(websocket, _prompt(cwd))
                        continue
                    if mtype == "command":
                        command = str(data.get("command") or "")
                    else:
                        continue
                else:
                    command = msg.strip()
            else:
                command = msg.strip()

            if not command:
                await _send_output(websocket, _prompt(cwd))
                continue

            # @ agent shortcuts — before blocklist / shell
            if command.startswith("@"):
                await _handle_at_command(
                    websocket, command=command, user=user, tenant_id=tenant_id
                )
                await _send_output(websocket, _prompt(cwd))
                continue

            if command.lower() == "help":
                await _send_output(
                    websocket,
                    "\r\nAvailable: kubectl, helm, terraform, git, aws, npm, pip\r\n"
                    "Commands are validated before execution.\r\n"
                    "Use @help for agent shortcuts.\r\n",
                )
                await _send_output(websocket, _prompt(cwd))
                continue

            if command.lower().startswith("cd"):
                parts = command.split(maxsplit=1)
                target = parts[1].strip() if len(parts) > 1 else os.path.expanduser("~")
                try:
                    new_path = os.path.abspath(os.path.join(cwd, target))
                    if os.path.isdir(new_path):
                        cwd = new_path
                        save_session_state(
                            session_id, {"cwd": cwd, "scrollback": scrollback[-8000:]}
                        )
                        await _send(websocket, {"type": "prompt", "prompt": _prompt(cwd)})
                    else:
                        await _send_output(websocket, f"\r\ncd: no such directory: {target}\r\n")
                except Exception as exc:
                    await _send_output(websocket, f"\r\ncd: {exc}\r\n")
                await _send_output(websocket, _prompt(cwd))
                continue

            if _is_blocked(command):
                await _send_output(
                    websocket,
                    f"\r\n🚫 Blocked: '{command}' is not permitted.\r\n{_prompt(cwd)}",
                )
                # Never store blocked commands in history
                continue

            from .command_validator import CommandValidator

            check = CommandValidator.validate_with_context(
                [command],
                role=user.role,
                environment=PlatformContext.current_env(),
                tool="shell",
                tenant_id=tenant_id,
            )
            if not check.safe:
                violations = "; ".join(check.violations or [])
                await _send_output(
                    websocket,
                    f"\r\n⛔ Validation failed: {violations}\r\n{_prompt(cwd)}",
                )
                continue

            if check.requires_approval:
                reasons = list(check.decision.reasons) if check.decision else []
                approval = create_terminal_approval(
                    tenant_id=tenant_id,
                    username=user.username,
                    command=command,
                    reasons=reasons,
                    session_id=session_id,
                )
                pending_approval_id = approval.id
                decision_event = asyncio.Event()
                decision_payload = None
                if unregister_waiter:
                    unregister_waiter()
                unregister_waiter = register_decision_waiter(approval.id, _on_decision)
                await _send(
                    websocket,
                    {
                        "type": "approval_required",
                        "approval_id": approval.id,
                        "command": command,
                        "reasons": reasons,
                    },
                )
                continue

            await _execute_shell_command(
                websocket,
                command=command,
                user=user,
                cwd=cwd,
                approved=False,
            )
            store_history(tenant_id=tenant_id, username=user.username, command=command)
            save_session_state(session_id, {"cwd": cwd, "scrollback": scrollback[-8000:]})
            await _send_output(websocket, _prompt(cwd))

    except WebSocketDisconnect:
        pass
    finally:
        if unregister_waiter:
            unregister_waiter()
        save_session_state(session_id, {"cwd": cwd, "scrollback": scrollback[-8000:]})
        try:
            await websocket.close()
        except Exception:
            pass


# Keep module exports used by tests
__all__ = [
    "router",
    "ws_broadcast",
    "broadcast_json",
    "send_to_user",
    "accept_portal_connection",
    "accept_agent_run_connection",
    "_is_blocked",
]
