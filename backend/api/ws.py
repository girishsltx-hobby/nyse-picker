"""WebSocket broadcast manager and endpoint."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()

_connections: list[WebSocket] = []
_lock = asyncio.Lock()


async def broadcast(payload: dict[str, Any]) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    message = json.dumps(payload)
    async with _lock:
        dead: list[WebSocket] = []
        for ws in _connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _connections.remove(ws)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    async with _lock:
        _connections.append(websocket)
    logger.info("WS client connected (%d total)", len(_connections))
    try:
        while True:
            # Keep the connection alive; clients can optionally send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        async with _lock:
            if websocket in _connections:
                _connections.remove(websocket)
        logger.info("WS client disconnected (%d total)", len(_connections))
