import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import Settings
from app.domain.errors import InvalidCredentials
from app.realtime import Hub
from app.security import decode_access_token

router = APIRouter()

UNAUTHORIZED = 4401


@router.websocket("/ws")
async def events(websocket: WebSocket) -> None:
    """Live updates. The token comes in the first message, not the URL: URLs end up in logs."""
    settings: Settings = websocket.app.state.settings
    hub: Hub = websocket.app.state.hub
    await websocket.accept()
    try:
        async with asyncio.timeout(5):
            hello = await websocket.receive_json()
        user_id = decode_access_token(str(hello.get("token", "")), settings.jwt_secret)
    except (TimeoutError, InvalidCredentials, ValueError, AttributeError):
        await websocket.close(code=UNAUTHORIZED)
        return
    except WebSocketDisconnect:
        return
    hub.connect(user_id, websocket)
    try:
        await websocket.send_json({"type": "ready"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(user_id, websocket)
