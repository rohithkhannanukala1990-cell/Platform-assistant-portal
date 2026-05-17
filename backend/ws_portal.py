"""In-memory WebSocket hub for portal push."""

from __future__ import annotations

from typing import Dict, List

from fastapi import WebSocket

_user_clients: Dict[str, List[WebSocket]] = {}


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


async def broadcast_json(payload: dict) -> None:
    """Fan-out JSON to ALL connected clients."""
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
