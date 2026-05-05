"""WebSocket endpoints."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/live")
async def live_websocket(websocket: WebSocket) -> None:
    event_bus = websocket.app.state.event_bus
    await event_bus.connect(websocket)
    await websocket.send_json({"event_type": "connected", "payload": {"stream": "live"}})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_bus.disconnect(websocket)
