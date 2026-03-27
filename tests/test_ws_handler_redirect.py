"""Tests for phx_join with both 'url' and 'redirect' payload fields.

The Phoenix LiveView JS client sends either 'url' or 'redirect' but never both.
"""

import json

from pyview.csrf import generate_csrf_token
from pyview.instrumentation import NoOpInstrumentation
from pyview.live_routes import LiveViewLookup
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


def make_handler():
    routes = LiveViewLookup()
    routes.add("/demo", MountingLiveView)
    return LiveSocketHandler(routes, NoOpInstrumentation())


async def test_phx_join_with_url_payload(monkeypatch):
    """Standard phx_join with 'url' field works (regression guard)."""
    handler = make_handler()
    websocket = make_join_websocket()

    async def noop_connected(topic, socket):
        pass

    monkeypatch.setattr(handler, "handle_connected", noop_connected)
    await handler.handle(websocket)

    websocket.send_text.assert_called_once()
    resp = json.loads(websocket.send_text.call_args[0][0])
    assert resp[3] == "phx_reply"
    assert resp[4]["status"] == "ok"
    assert "rendered" in resp[4]["response"]


async def test_phx_join_missing_url_and_redirect_closes_socket():
    """phx_join with neither 'url' nor 'redirect' closes the websocket."""
    handler = make_handler()
    payload = {
        "params": {"_csrf_token": generate_csrf_token("lv:test")},
    }
    websocket = make_join_websocket(payload)

    await handler.handle(websocket)

    websocket.close.assert_called_once()


async def test_phx_join_with_redirect_payload(monkeypatch):
    """phx_join with 'redirect' field instead of 'url' works.

    The JS client sends 'redirect' (not 'url') when this.redirect is true
    (e.g. during live_redirect navigation).
    """
    handler = make_handler()
    payload = {
        "redirect": "http://testserver/demo",
        "params": {"_csrf_token": generate_csrf_token("lv:test")},
    }
    websocket = make_join_websocket(payload)

    async def noop_connected(topic, socket):
        pass

    monkeypatch.setattr(handler, "handle_connected", noop_connected)
    await handler.handle(websocket)

    websocket.send_text.assert_called_once()
    resp = json.loads(websocket.send_text.call_args[0][0])
    assert resp[3] == "phx_reply"
    assert resp[4]["status"] == "ok"
    assert "rendered" in resp[4]["response"]
