import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pyview.csrf import generate_csrf_token
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler


class EmptyRendered:
    def tree(self):
        return {}

    def text(self, socket=None):
        return ""


class MountingLiveView(LiveView[dict]):
    async def mount(self, socket, session):
        socket.context = {}

    async def render(self, assigns, meta):
        return EmptyRendered()


async def test_handle_closes_socket_when_connected_loop_errors(monkeypatch):
    routes = LiveViewLookup()
    routes.add("/demo", MountingLiveView)
    handler = LiveSocketHandler(routes, NoOpInstrumentation())

    websocket = MagicMock()
    websocket.accept = AsyncMock()
    websocket.send_text = AsyncMock()
    websocket.receive_text = AsyncMock(
        return_value=json.dumps(
            [
                "1",
                "1",
                "lv:test",
                "phx_join",
                {
                    "url": "http://testserver/demo",
                    "params": {"_csrf_token": generate_csrf_token("lv:test")},
                },
            ]
        )
    )

    closed = []

    async def fake_close(self):
        closed.append(self)

    async def fail_handle_connected(topic, socket):
        raise RuntimeError("boom")

    monkeypatch.setattr(ConnectedLiveViewSocket, "close", fake_close)
    monkeypatch.setattr(handler, "handle_connected", fail_handle_connected)

    with pytest.raises(RuntimeError, match="boom"):
        await handler.handle(websocket)

    assert len(closed) == 1
    assert handler.sessions == 0
