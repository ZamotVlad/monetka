from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.realtime import Hub
from app.security import create_access_token


def token_for(app: FastAPI) -> tuple[str, str]:
    user_id = uuid4()
    return str(user_id), create_access_token(user_id, app.state.settings.jwt_secret, 5)


def test_signed_in_socket_receives_its_events(app: FastAPI) -> None:
    user_id, token = token_for(app)
    hub: Hub = app.state.hub
    with TestClient(app).websocket_connect("/api/v1/ws") as socket:
        socket.send_json({"token": token})
        assert socket.receive_json() == {"type": "ready"}
        assert hub.online == 1

        event = {"id": 1, "type": "wallet.changed", "payload": {"user_id": user_id}}
        # The app runs on the test client's own event loop, so the hub is called there
        socket.portal.call(hub.dispatch, event)
        assert socket.receive_json() == event
    assert hub.online == 0


def test_socket_without_valid_token_is_closed(app: FastAPI) -> None:
    with TestClient(app).websocket_connect("/api/v1/ws") as socket:
        socket.send_json({"token": "nonsense"})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == 4401


async def test_hub_ignores_events_for_offline_users() -> None:
    await Hub().dispatch({"type": "wallet.changed", "payload": {"user_id": str(uuid4())}})
