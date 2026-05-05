"""In-process WebSocket event fanout for live API updates."""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket


class LiveEventBus:
    """Small in-process broadcaster used until Redis/event streaming is introduced."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, event_type: str, payload: dict[str, Any]) -> None:
        disconnected: list[WebSocket] = []
        for websocket in self._connections:
            try:
                await websocket.send_json({"event_type": event_type, "payload": payload})
            except Exception:
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)
