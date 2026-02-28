"""
TWINFORGE Agent 3 — WebSocket Manager
Manages WebSocket connections and broadcasts telemetry to all connected clients.
"""

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for real-time telemetry streaming.

    Handles client connect/disconnect and broadcasts telemetry data
    to all connected clients concurrently.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (total: %d)", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info("WebSocket client disconnected (total: %d)", len(self._connections))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """
        Broadcast data to all connected WebSocket clients.

        Automatically removes clients that have disconnected.
        """
        if not self._connections:
            return

        message = json.dumps(data, default=str)
        disconnected: list[WebSocket] = []

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws)

    async def send_to(self, websocket: WebSocket, data: dict[str, Any]) -> bool:
        """Send data to a specific WebSocket client."""
        try:
            await websocket.send_text(json.dumps(data, default=str))
            return True
        except Exception:
            self.disconnect(websocket)
            return False

    @property
    def connection_count(self) -> int:
        """Number of active WebSocket connections."""
        return len(self._connections)
