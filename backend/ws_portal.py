"""In-memory WebSocket hub for portal push (e.g. health_alert)."""

from __future__ import annotations

from typing import List

from fastapi import WebSocket

_clients: List[WebSocket] = []


async def accept_portal_connection(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        try:
            _clients.remove(websocket)
        except ValueError:
            pass


async def broadcast_json(payload: dict) -> None:
    """Fan-out JSON to all connected portal clients; drop broken sockets."""
    dead: List[WebSocket] = []
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        try:
            _clients.remove(ws)
        except ValueError:
            pass
