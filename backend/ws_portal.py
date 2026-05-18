"""In-memory WebSocket hub for portal push and agent-run streaming."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from .auth import User, decode_token
from .database import AgentRun, engine

_user_clients: Dict[str, List[WebSocket]] = {}
_run_watchers: Dict[str, List[WebSocket]] = {}

TERMINAL_STATUSES = frozenset({"success", "failed", "pending_approval"})
POLL_INTERVAL_S = 1.5
MAX_WATCH_S = 120.0

router = APIRouter(tags=["websocket"])


def _authenticate_ws_token(token: str) -> Optional[User]:
    """Validate JWT using the same logic as get_current_user (query-param token)."""
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


async def accept_portal_connection(
    websocket: WebSocket,
    user_id: str = "anonymous",
) -> None:
    await websocket.accept()
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


async def accept_agent_run_connection(
    websocket: WebSocket,
    run_id: str,
    token: str = "",
) -> None:
    user = _authenticate_ws_token(token)
    if not user:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close()
        return

    await websocket.accept()
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
async def agent_run_ws(
    websocket: WebSocket,
    run_id: str,
    token: str = Query(default=""),
):
    await accept_agent_run_connection(websocket, run_id, token=token)


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
