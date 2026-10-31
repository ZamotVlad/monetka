import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class Hub:
    """Open WebSocket connections of this process, grouped by user."""

    def __init__(self) -> None:
        self._connections: defaultdict[UUID, set[WebSocket]] = defaultdict(set)

    def connect(self, user_id: UUID, websocket: WebSocket) -> None:
        self._connections[user_id].add(websocket)

    def disconnect(self, user_id: UUID, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]

    @property
    def online(self) -> int:
        return sum(len(sockets) for sockets in self._connections.values())

    async def send(self, user_id: UUID, message: dict[str, Any]) -> None:
        for websocket in list(self._connections.get(user_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:  # the client went away mid-send
                self.disconnect(user_id, websocket)

    async def dispatch(self, event: dict[str, Any]) -> None:
        user_id = event.get("payload", {}).get("user_id")
        if user_id:
            await self.send(UUID(user_id), event)
