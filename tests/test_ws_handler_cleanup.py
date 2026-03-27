import pytest

from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
from pyview.live_socket import ConnectedLiveViewSocket
from pyview.live_view import LiveView
from pyview.ws_handler import LiveSocketHandler

from .ws_mock import make_join_websocket


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

    websocket = make_join_websocket()

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
