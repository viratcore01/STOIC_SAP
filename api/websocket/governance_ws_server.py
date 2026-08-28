"""Governance WebSocket Server — Live state push channel for Fiori/React UI.

Receives state-change events from the Orchestrator and pushes them
to the connected Governance UI clients in real-time.
"""

from __future__ import annotations

import json
from typing import Optional

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)
app = FastAPI(title="CCRO Governance WebSocket", version="0.1.0")


class ConnectionManager:
    """Manages WebSocket connections for the Governance UI."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, thread_id: str) -> None:
        await websocket.accept()
        self.active_connections.setdefault(thread_id, []).append(websocket)
        logger.info("ws.connected", thread_id=thread_id)

    def disconnect(self, websocket: WebSocket, thread_id: str) -> None:
        if thread_id in self.active_connections:
            self.active_connections[thread_id] = [
                ws for ws in self.active_connections[thread_id] if ws != websocket
            ]
        logger.info("ws.disconnected", thread_id=thread_id)

    async def broadcast_state(self, thread_id: str, state: dict) -> None:
        """Broadcast state update to all connected clients for a thread."""
        if thread_id not in self.active_connections:
            return

        dead = []
        for ws in self.active_connections[thread_id]:
            try:
                await ws.send_json(state)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            self.active_connections[thread_id].remove(ws)

    async def send_approval_card(self, thread_id: str, card: dict) -> None:
        """Push an Approval Card to the Governance UI."""
        await self.broadcast_state(
            thread_id,
            {"type": "approval_card", "data": card},
        )


manager = ConnectionManager()


@app.websocket("/ws/governance/{thread_id}")
async def governance_websocket(websocket: WebSocket, thread_id: str) -> None:
    """WebSocket endpoint for Governance UI live updates."""
    await manager.connect(websocket, thread_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle incoming messages from the UI
            if message.get("type") == "approval_decision":
                # Forward to the Orchestrator
                logger.info(
                    "ws.approval_received",
                    thread_id=thread_id,
                    decision=message.get("decision"),
                )
                await websocket.send_json({"type": "ack", "status": "received"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, thread_id)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
